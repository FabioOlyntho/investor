"""Page 4: Market Signals — How the markets are doing today."""

import pandas as pd
import streamlit as st

from components.charts import (
    regime_gauge, sector_momentum_bar, theme_momentum_bar,
    vix_chart, yield_curve_chart,
)
from config.settings import THEME_ETFS
from data.calculations import market_regime_score
from data.market_data import (
    fetch_benchmark_indices, fetch_fx_daily_changes,
    fetch_morningstar_ratings, fetch_sector_performance,
    fetch_theme_performance, fetch_vix,
    fetch_yield_curve, fetch_yield_curve_historical,
)


def render():
    st.header("What's Happening in the Markets")

    # Fetch data
    vix_data = fetch_vix(period="6mo")
    yields_current = fetch_yield_curve()
    yields_hist = fetch_yield_curve_historical(months_ago=3)
    sector_perf = fetch_sector_performance(period="1mo")

    # Compute regime score
    current_vix = None
    if not vix_data.empty:
        current_vix = vix_data["Close"].iloc[-1]

    yield_spread = None
    if "10Y" in yields_current and "2Y" in yields_current:
        yield_spread = yields_current["10Y"] - yields_current["2Y"]

    momentum_positive = None
    if sector_perf:
        positive = sum(1 for v in sector_perf.values() if v > 0)
        momentum_positive = positive / len(sector_perf)

    regime = market_regime_score(
        vix=current_vix,
        yield_spread=yield_spread,
        momentum_pct_positive=momentum_positive,
    )

    # --- Market Mood ---
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Market Mood")
        fig = regime_gauge(regime, title="Confidence Level")
        st.plotly_chart(fig, use_container_width=True)

        if regime < 33:
            label, color = "Pessimistic", "#FF1744"
            st.caption("Markets are scared — investors are selling, being cautious.")
        elif regime < 66:
            label, color = "Mixed Feelings", "#FFD600"
            st.caption("Markets are undecided — some good, some bad signals.")
        else:
            label, color = "Optimistic", "#00C853"
            st.caption("Markets are confident — investors are buying, feeling good.")

        st.markdown(
            f"<h3 style='text-align:center;color:{color}'>{label}</h3>",
            unsafe_allow_html=True,
        )

        if current_vix is not None:
            vix_label = "Calm" if current_vix < 15 else ("Cautious" if current_vix < 25 else "Scared")
            st.metric("Fear Index (VIX)", f"{current_vix:.1f}", help=f"Markets are: {vix_label}. Below 15 = calm, 15-25 = cautious, above 25 = scared.")
        if yield_spread is not None:
            spread_label = "Normal" if yield_spread > 0 else "Warning sign"
            st.metric("Interest Rate Gap (10Y-2Y)", f"{yield_spread:.2f}%", help=f"{spread_label}. When this goes negative, it often means a recession is coming.")
        if momentum_positive is not None:
            st.metric("Sectors Going Up", f"{momentum_positive*100:.0f}%", help="What % of market sectors gained this month. Higher = healthier market.")

    with col2:
        fig = vix_chart(vix_data, title="Fear Index Over Time (lower = calmer)")
        st.plotly_chart(fig, use_container_width=True)

    # --- Major Indices ---
    st.divider()
    st.subheader("Major Stock Markets")
    st.caption("How the big indices are doing — compare your portfolio to these.")

    indices = fetch_benchmark_indices()
    if indices:
        idx_cols = st.columns(len(indices))
        for i, (name, data) in enumerate(indices.items()):
            with idx_cols[i]:
                st.metric(
                    name,
                    f"{data['value']:,.0f}",
                    f"{data['change_pct']:+.2f}%",
                    delta_color="normal",
                )
    else:
        st.warning("Could not load index data.")

    st.divider()

    col3, col4 = st.columns(2)

    with col3:
        # Yield curve
        if yields_current:
            st.caption("US interest rates at different time horizons. When the line goes down (inverted), it's a warning sign.")
            fig = yield_curve_chart(yields_current, yields_hist, title="US Interest Rates (Now vs 3 Months Ago)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Could not fetch interest rate data.")

    with col4:
        # Sector momentum
        if sector_perf:
            st.caption("Which parts of the economy are winning or losing this month.")
            fig = sector_momentum_bar(sector_perf, title="Sectors: Who's Winning This Month")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Could not fetch sector data.")

    # --- Theme Performance ---
    st.divider()
    st.subheader("Your Investment Themes")
    st.caption("How the areas related to your investments are doing over the last month. Red = losing, green = gaining.")

    theme_perf = fetch_theme_performance(period="1mo")
    if theme_perf:
        fig = theme_momentum_bar(theme_perf, THEME_ETFS, title="Themes: Last Month Performance")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Could not fetch theme data.")

    # --- FX Monitor ---
    st.divider()
    st.subheader("Currency Exchange Rates")
    st.caption("Changes in currency rates affect the value of your non-euro investments.")

    fx_data = fetch_fx_daily_changes()
    if fx_data:
        fx_cols = st.columns(len(fx_data))
        for i, (pair, data) in enumerate(fx_data.items()):
            with fx_cols[i]:
                rate = data["rate"]
                change = data["change_pct"]
                st.metric(
                    pair,
                    f"{rate:.4f}",
                    f"{change:+.2f}% today",
                    delta_color="normal",
                    help=f"How many {pair.split('/')[1]} you get for 1 {pair.split('/')[0]}. Green = euro stronger, red = euro weaker.",
                )
    else:
        st.warning("Could not fetch currency data.")

    # --- Morningstar Ratings ---
    st.divider()
    st.subheader("Fund Quality Ratings (Morningstar)")
    st.caption("Morningstar is like a restaurant guide for funds — more stars = better rated. Watch for downgrades.")

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
                "Below Average": "Low risk",
                "Average": "Normal risk",
                "Above Average": "Higher risk",
                "High": "High risk",
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
