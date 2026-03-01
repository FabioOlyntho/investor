"""Single-page dashboard — scroll down to see everything about your portfolio and the markets."""

import numpy as np
import pandas as pd
import streamlit as st

from components.charts import (
    allocation_donut, correlation_heatmap, cumulative_returns_chart,
    drawdown_chart, monthly_heatmap, pnl_bar_chart,
    portfolio_value_chart, regime_gauge, return_distribution_histogram,
    sector_exposure_bar, sector_momentum_bar, theme_momentum_bar,
    vix_chart, yield_curve_chart,
)
from components.formatters import fmt_currency, fmt_percent
from config.settings import (
    BENCHMARK_INDICES, FX_PAIRS, SEVERITY_COLORS, THEME_ETFS,
)
from data.calculations import (
    annualized_return, annualized_volatility, beta,
    correlation_matrix, daily_returns, drawdown_series,
    market_regime_score, max_drawdown, rolling_volatility,
    sharpe_ratio, value_at_risk,
)
from data.database import get_alert_history, get_positions
from data.market_data import (
    convert_to_eur, fetch_benchmark_history, fetch_benchmark_indices,
    fetch_current_prices, fetch_fx_daily_changes, fetch_fx_rates,
    fetch_morningstar_ratings, fetch_multi_history, fetch_price_history,
    fetch_sector_performance, fetch_theme_performance, fetch_vix,
    fetch_yield_curve, fetch_yield_curve_historical,
)


def render():
    positions = get_positions()
    if positions.empty:
        st.info("No positions in portfolio. Go to **Portfolio Management** to add some.")
        return

    tickers = tuple(positions["ticker"].tolist())
    unique_tickers = tuple(dict.fromkeys(tickers))

    # Fetch core data
    prices = fetch_current_prices(unique_tickers)
    fx_rates = fetch_fx_rates()
    if not prices:
        st.warning("Could not fetch current prices. Please try again.")
        return

    # ─── PORTFOLIO METRICS ───────────────────────────────────────────
    rows = []
    notes_map = {}
    for _, pos in positions.iterrows():
        ticker = pos["ticker"]
        notes_map[ticker] = (pos.get("notes") or "").strip()
        if ticker not in prices:
            continue
        p = prices[ticker]
        native_currency = p["currency"]
        price_eur = convert_to_eur(p["price"], native_currency, fx_rates)
        change_eur = convert_to_eur(p["change"], native_currency, fx_rates)
        market_value = pos["units"] * price_eur
        pnl = market_value - pos["cost_basis"]
        pnl_pct = (pnl / pos["cost_basis"] * 100) if pos["cost_basis"] > 0 else 0
        daily_chg = pos["units"] * change_eur

        rows.append({
            "ticker": ticker, "name": pos["name"], "units": pos["units"],
            "price": price_eur, "native_price": p["price"],
            "native_currency": native_currency, "cost_basis": pos["cost_basis"],
            "market_value": market_value, "pnl": pnl, "pnl_pct": pnl_pct,
            "daily_change": daily_chg, "daily_change_pct": p["change_pct"],
            "sector": pos["sector"], "asset_class": pos["asset_class"],
        })

    if not rows:
        st.warning("No valid price data for portfolio positions.")
        return

    port_df = pd.DataFrame(rows)
    total_value = port_df["market_value"].sum()
    total_cost = port_df["cost_basis"].sum()
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    daily_change = port_df["daily_change"].sum()
    daily_change_pct = (daily_change / (total_value - daily_change) * 100) if total_value != daily_change else 0

    # Fetch history for charts and calculations
    hist = fetch_multi_history(unique_tickers, period="1y")

    # Sharpe from historical data
    port_sharpe = None
    port_returns = None
    available = []
    w = None
    if not hist.empty and len(hist) > 30:
        weights = {}
        for _, row in port_df.iterrows():
            weights[row["ticker"]] = weights.get(row["ticker"], 0) + row["market_value"]
        total_w = sum(weights.values())
        if total_w > 0:
            available = [t for t in unique_tickers if t in hist.columns]
            if available:
                w = pd.Series({t: weights.get(t, 0) / total_w for t in available})
                returns_df = hist[available].ffill().pct_change().fillna(0)
                port_returns = (returns_df * w).sum(axis=1)
                port_sharpe = sharpe_ratio(port_returns)

    # ─── TOP METRICS ROW ─────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Value", fmt_currency(total_value),
                  delta=fmt_percent(daily_change_pct))
    with c2:
        st.metric("Today's Change", fmt_currency(daily_change),
                  delta=fmt_percent(daily_change_pct))
    with c3:
        st.metric("Total Gain/Loss", fmt_currency(total_pnl),
                  delta=fmt_percent(total_pnl_pct))
    with c4:
        sharpe_str = f"{port_sharpe:.2f}" if port_sharpe is not None else "N/A"
        st.metric("Sharpe Ratio", sharpe_str,
                  help="Risk-adjusted return. Above 1 = good, above 2 = great.")

    # ─── ACTIVE ALERTS BANNER ────────────────────────────────────────
    unack = get_alert_history(limit=50, unacknowledged_only=True)
    if not unack.empty:
        critical = unack[unack["severity"] == "critical"]
        warning = unack[unack["severity"] == "warning"]
        if not critical.empty:
            for _, alert in critical.iterrows():
                st.error(f"**{alert['message']}**", icon="\u26a0\ufe0f")
        if not warning.empty:
            for _, alert in warning.iterrows():
                st.warning(f"{alert['message']}")

    st.divider()

    # ─── PORTFOLIO VALUE VS INDICES ──────────────────────────────────
    if not hist.empty and port_returns is not None and available:
        cb_weights = {}
        for _, row in port_df.iterrows():
            cb_weights[row["ticker"]] = cb_weights.get(row["ticker"], 0) + row["cost_basis"]
        total_cb = sum(cb_weights.get(t, 0) for t in available)
        if total_cb > 0:
            w_cb = pd.Series({t: cb_weights.get(t, 0) / total_cb for t in available})
            returns_df = hist[available].ffill().pct_change().fillna(0)
            port_ret = (returns_df * w_cb).sum(axis=1)
            cum = (1 + port_ret).cumprod()
            if len(cum) > 0 and cum.iloc[-1] != 0:
                port_value_series = total_value * cum / cum.iloc[-1]

                benchmarks = {}
                for idx_name, idx_ticker in BENCHMARK_INDICES.items():
                    try:
                        idx_hist = fetch_price_history(idx_ticker, period="1y")
                        if not idx_hist.empty:
                            idx_norm = idx_hist["Close"] / idx_hist["Close"].iloc[-1] * total_value
                            benchmarks[idx_name] = idx_norm.reindex(
                                port_value_series.index, method="ffill"
                            )
                    except Exception:
                        continue

                fig = portfolio_value_chart(
                    port_value_series.index, port_value_series,
                    benchmarks=benchmarks,
                    title="Your Portfolio vs Major Indices (1 Year)",
                )
                st.plotly_chart(fig, use_container_width=True)

    # ─── ALLOCATION & P&L ────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        alloc = port_df.groupby("sector")["market_value"].sum()
        alloc_pct = (alloc / total_value * 100).sort_values(ascending=False)
        fig = allocation_donut(alloc_pct.index.tolist(), alloc_pct.values.tolist(),
                               title="Where Your Money Is")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        sorted_df = port_df.sort_values("pnl")
        labels = [f"{r['ticker']}" if len(r['ticker']) <= 10 else r['name'][:20]
                  for _, r in sorted_df.iterrows()]
        fig = pnl_bar_chart(labels, sorted_df["pnl"].tolist(),
                            title="Gain/Loss Per Position")
        st.plotly_chart(fig, use_container_width=True)

    # ─── MARKET MOOD ─────────────────────────────────────────────────
    st.divider()
    st.subheader("What's Happening in the Markets")

    vix_data = fetch_vix(period="6mo")
    yields_current = fetch_yield_curve()
    yields_hist = fetch_yield_curve_historical(months_ago=3)
    sector_perf = fetch_sector_performance(period="1mo")

    current_vix = vix_data["Close"].iloc[-1] if not vix_data.empty else None
    yield_spread = None
    if "10Y" in yields_current and "2Y" in yields_current:
        yield_spread = yields_current["10Y"] - yields_current["2Y"]
    momentum_positive = None
    if sector_perf:
        positive = sum(1 for v in sector_perf.values() if v > 0)
        momentum_positive = positive / len(sector_perf)

    regime = market_regime_score(
        vix=current_vix, yield_spread=yield_spread,
        momentum_pct_positive=momentum_positive,
    )

    col_m1, col_m2, col_m3 = st.columns([1, 1, 1])

    with col_m1:
        fig = regime_gauge(regime, title="Market Mood")
        st.plotly_chart(fig, use_container_width=True)
        if regime < 33:
            st.caption("Markets are scared — investors are selling, being cautious.")
        elif regime < 66:
            st.caption("Markets are undecided — some good, some bad signals.")
        else:
            st.caption("Markets are confident — investors are buying, feeling good.")

    with col_m2:
        # Major indices
        indices = fetch_benchmark_indices()
        if indices:
            for name, data in indices.items():
                st.metric(name, f"{data['value']:,.0f}",
                         f"{data['change_pct']:+.2f}%", delta_color="normal")
        else:
            st.info("Index data unavailable")

    with col_m3:
        if current_vix is not None:
            vix_label = "Calm" if current_vix < 15 else ("Cautious" if current_vix < 25 else "Scared")
            st.metric("Fear Index (VIX)", f"{current_vix:.1f}",
                     help=f"Markets are: {vix_label}. Below 15 = calm, 15-25 = cautious, above 25 = scared.")
        if yield_spread is not None:
            spread_label = "Normal" if yield_spread > 0 else "Warning sign"
            st.metric("Interest Rate Gap", f"{yield_spread:.2f}%",
                     help=f"{spread_label}. When this goes negative, it often means a recession is coming.")
        if momentum_positive is not None:
            st.metric("Sectors Going Up", f"{momentum_positive*100:.0f}%",
                     help="What % of market sectors gained this month.")

    # VIX chart + Sectors
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        fig = vix_chart(vix_data, title="Fear Index Over Time")
        st.plotly_chart(fig, use_container_width=True)
    with col_v2:
        if sector_perf:
            fig = sector_momentum_bar(sector_perf, title="Sectors: Who's Winning This Month")
            st.plotly_chart(fig, use_container_width=True)

    # Themes + FX
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        theme_perf = fetch_theme_performance(period="1mo")
        if theme_perf:
            st.caption("How the areas related to your investments are doing.")
            fig = theme_momentum_bar(theme_perf, THEME_ETFS,
                                     title="Your Themes: Last Month")
            st.plotly_chart(fig, use_container_width=True)

    with col_t2:
        st.caption("Currency changes affect the value of your non-euro investments.")
        fx_data = fetch_fx_daily_changes()
        if fx_data:
            for pair, data in fx_data.items():
                rate = data["rate"]
                change = data["change_pct"]
                st.metric(pair, f"{rate:.4f}", f"{change:+.2f}% today",
                         delta_color="normal")

    # Interest rates
    if yields_current:
        col_y1, col_y2 = st.columns(2)
        with col_y1:
            st.caption("US interest rates at different time horizons.")
            fig = yield_curve_chart(yields_current, yields_hist,
                                    title="Interest Rates (Now vs 3 Months Ago)")
            st.plotly_chart(fig, use_container_width=True)
        with col_y2:
            sector_weights = port_df.groupby("sector")["market_value"].sum()
            sector_pct = (sector_weights / total_value * 100).sort_values(ascending=False)
            fig = sector_exposure_bar(sector_pct.index.tolist(),
                                      sector_pct.values.tolist(),
                                      title="Your Sector Breakdown")
            st.plotly_chart(fig, use_container_width=True)

    # ─── PERFORMANCE ─────────────────────────────────────────────────
    st.divider()
    st.subheader("How Your Portfolio Has Performed")

    if port_returns is not None and len(port_returns) > 10:
        # Benchmark for comparison
        bench = fetch_benchmark_history(period="1y")
        bench_returns = None
        port_beta = None
        if not bench.empty:
            bench_returns = daily_returns(bench["Close"])
            bench_returns = bench_returns.reindex(port_returns.index).dropna()
            if len(bench_returns) > 10:
                port_beta = beta(port_returns, bench_returns)

        # Key metrics
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Yearly Return", f"{annualized_return(port_returns)*100:.2f}%",
                     help="Your annualized return — what you'd earn if this pace continued for a year.")
        with c2:
            vol = annualized_volatility(port_returns) * 100
            st.metric("Volatility", f"{vol:.2f}%",
                     help="How much your portfolio swings up and down. Lower = smoother ride.")
        with c3:
            port_prices = (1 + port_returns).cumprod()
            mdd = max_drawdown(port_prices) * 100
            st.metric("Biggest Drop", f"{mdd:.1f}%",
                     help="The worst fall from a peak. Shows your downside risk.")
        with c4:
            var95 = value_at_risk(port_returns) * 100
            st.metric("Worst Day (95%)", f"{var95:.2f}%",
                     help="On 95% of days, your losses won't exceed this amount.")

        # Cumulative returns
        fig = cumulative_returns_chart(port_returns, bench_returns,
                                        title="Growth of Your Portfolio vs Benchmark")
        st.plotly_chart(fig, use_container_width=True)

        # Heatmap + Distribution
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            fig = monthly_heatmap(port_returns, title="Monthly Returns")
            st.plotly_chart(fig, use_container_width=True)
        with col_p2:
            fig = return_distribution_histogram(port_returns,
                                                title="Daily Returns Distribution")
            st.plotly_chart(fig, use_container_width=True)

        # Drawdown + Correlation
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            dd = drawdown_series(port_prices)
            fig = drawdown_chart(dd, title="Drawdown From Peak")
            st.plotly_chart(fig, use_container_width=True)
        with col_r2:
            if len(available) >= 2:
                corr = correlation_matrix(hist[available])
                fig = correlation_heatmap(corr, title="How Your Positions Move Together")
                st.plotly_chart(fig, use_container_width=True)

        # Rolling volatility
        roll_vol = rolling_volatility(port_returns, window=30) * 100
        st.caption("How unstable your portfolio has been over the last 30 days — spikes mean more risk.")
        from components.charts import rolling_metric_chart
        fig = rolling_metric_chart(roll_vol, title="Portfolio Instability (30-Day Rolling)",
                                   ylabel="Volatility (%)")
        st.plotly_chart(fig, use_container_width=True)

    # ─── TOP MOVERS TABLE ────────────────────────────────────────────
    st.divider()
    st.subheader("All Your Positions")

    movers = port_df[["ticker", "name", "price", "daily_change", "daily_change_pct",
                       "market_value", "pnl", "pnl_pct"]].copy()
    movers["bank"] = movers["ticker"].map(notes_map)
    movers = movers.sort_values("daily_change_pct", ascending=False)
    movers = movers[["ticker", "name", "bank", "price", "daily_change", "daily_change_pct",
                      "market_value", "pnl", "pnl_pct"]]
    movers.columns = ["Ticker", "Name", "Bank", "Price (EUR)", "Today", "Today %",
                      "Value", "Gain/Loss", "Gain/Loss %"]

    st.dataframe(
        movers.style.applymap(
            lambda v: "color: #00C853" if isinstance(v, (int, float)) and v > 0
            else ("color: #FF1744" if isinstance(v, (int, float)) and v < 0 else ""),
            subset=["Today", "Today %", "Gain/Loss", "Gain/Loss %"]
        ).format({
            "Price (EUR)": "{:.2f}",
            "Today": "{:+.2f}",
            "Today %": "{:+.2f}%",
            "Value": "{:,.2f}",
            "Gain/Loss": "{:+,.2f}",
            "Gain/Loss %": "{:+.2f}%",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # ─── MORNINGSTAR ─────────────────────────────────────────────────
    st.divider()
    st.subheader("Fund Quality Ratings")
    st.caption("Morningstar is like a restaurant guide for funds — more stars = better rated.")

    mstar = fetch_morningstar_ratings()
    if mstar:
        mstar_rows = []
        for f in mstar:
            stars = f.get("star_rating")
            star_display = ("+" * stars) if stars else "N/A"
            prev = f.get("previous_star_rating")
            change = ""
            if stars and prev and prev != stars:
                diff = stars - prev
                change = f"{'went up' if diff > 0 else 'went down'} {abs(diff)}"

            risk = f.get("risk_rating") or "N/A"
            risk_plain = {
                "Below Average": "Low risk", "Average": "Normal risk",
                "Above Average": "Higher risk", "High": "High risk",
                "Low": "Very low risk",
            }.get(risk, risk)

            mstar_rows.append({
                "Fund": f.get("fund_name", f.get("isin", ""))[:40],
                "Stars": star_display,
                "Change": change,
                "Type": (f.get("category") or "")[:30],
                "Analyst Pick": f.get("medalist_rating") or "N/A",
                "Risk Level": risk_plain,
            })

        if mstar_rows:
            mstar_df = pd.DataFrame(mstar_rows)
            st.dataframe(mstar_df, use_container_width=True, hide_index=True)
    else:
        st.info("Fund ratings unavailable. Make sure mstarpy is installed.")


render()
