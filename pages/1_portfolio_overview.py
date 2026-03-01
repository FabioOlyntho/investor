"""Page 1: Portfolio Overview — Metrics + 4 charts."""

import pandas as pd
import streamlit as st

from components.charts import (
    allocation_donut, pnl_bar_chart, portfolio_value_chart, sector_exposure_bar,
)
from components.formatters import fmt_currency, fmt_percent
from components.metrics import portfolio_metrics_row
from data.calculations import daily_returns, sharpe_ratio
from data.database import get_positions
from data.market_data import fetch_current_prices, fetch_multi_history, fetch_benchmark_history


def render():
    st.header("Portfolio Overview")

    positions = get_positions()
    if positions.empty:
        st.info("No positions in portfolio. Go to **Portfolio Management** to add some.")
        return

    tickers = tuple(positions["ticker"].tolist())

    # Fetch prices
    prices = fetch_current_prices(tickers)
    if not prices:
        st.warning("Could not fetch current prices. Please try again.")
        return

    # Calculate portfolio metrics
    rows = []
    for _, pos in positions.iterrows():
        ticker = pos["ticker"]
        if ticker not in prices:
            continue
        p = prices[ticker]
        market_value = pos["units"] * p["price"]
        pnl = market_value - pos["cost_basis"]
        pnl_pct = (pnl / pos["cost_basis"] * 100) if pos["cost_basis"] > 0 else 0
        daily_chg = pos["units"] * p["change"]
        rows.append({
            "ticker": ticker,
            "name": pos["name"],
            "units": pos["units"],
            "price": p["price"],
            "cost_basis": pos["cost_basis"],
            "market_value": market_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "daily_change": daily_chg,
            "daily_change_pct": p["change_pct"],
            "sector": pos["sector"],
            "asset_class": pos["asset_class"],
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

    # Sharpe from historical data
    hist = fetch_multi_history(tickers, period="1y")
    port_sharpe = None
    if not hist.empty and len(hist) > 30:
        # Weight by market value
        weights = {}
        for _, row in port_df.iterrows():
            weights[row["ticker"]] = row["market_value"]
        total_w = sum(weights.values())
        if total_w > 0:
            available = [t for t in tickers if t in hist.columns]
            if available:
                w = pd.Series({t: weights.get(t, 0) / total_w for t in available})
                returns_df = hist[available].pct_change().dropna()
                port_returns = (returns_df * w).sum(axis=1)
                port_sharpe = sharpe_ratio(port_returns)

    # Metrics row
    portfolio_metrics_row(
        total_value=total_value,
        daily_change=daily_change,
        daily_change_pct=daily_change_pct,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        sharpe=port_sharpe,
    )

    st.divider()

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        # Portfolio value over time
        if not hist.empty:
            available = [t for t in tickers if t in hist.columns]
            if available:
                weights = {}
                for _, row in port_df.iterrows():
                    if row["ticker"] in available:
                        weights[row["ticker"]] = row["units"]

                port_value_series = pd.Series(0.0, index=hist.index)
                for t in available:
                    port_value_series += hist[t] * weights.get(t, 0)

                bench = fetch_benchmark_history(period="1y")
                bench_series = None
                if not bench.empty:
                    bench_norm = bench["Close"] / bench["Close"].iloc[0] * port_value_series.iloc[0]
                    bench_series = bench_norm.reindex(port_value_series.index, method="ffill")

                fig = portfolio_value_chart(
                    port_value_series.index, port_value_series,
                    benchmark=bench_series,
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough history for value chart")

    with col2:
        # Asset allocation donut
        alloc = port_df.groupby("sector")["market_value"].sum()
        alloc_pct = (alloc / total_value * 100).sort_values(ascending=False)
        fig = allocation_donut(alloc_pct.index.tolist(), alloc_pct.values.tolist())
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        # P&L per position
        sorted_df = port_df.sort_values("pnl")
        fig = pnl_bar_chart(
            sorted_df["ticker"].tolist(),
            sorted_df["pnl"].tolist(),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        # Sector exposure
        sector_weights = port_df.groupby("sector")["market_value"].sum()
        sector_pct = (sector_weights / total_value * 100).sort_values(ascending=False)
        fig = sector_exposure_bar(
            sector_pct.index.tolist(),
            sector_pct.values.tolist(),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Top movers table
    st.subheader("Top Movers")
    movers = port_df[["ticker", "name", "price", "daily_change", "daily_change_pct",
                       "market_value", "pnl", "pnl_pct"]].copy()
    movers = movers.sort_values("daily_change_pct", ascending=False)
    movers.columns = ["Ticker", "Name", "Price", "Day Chg", "Day %",
                      "Mkt Value", "P&L", "P&L %"]

    st.dataframe(
        movers.style.applymap(
            lambda v: "color: #00C853" if isinstance(v, (int, float)) and v > 0
            else ("color: #FF1744" if isinstance(v, (int, float)) and v < 0 else ""),
            subset=["Day Chg", "Day %", "P&L", "P&L %"]
        ).format({
            "Price": "{:.2f}",
            "Day Chg": "{:+.2f}",
            "Day %": "{:+.2f}%",
            "Mkt Value": "{:,.2f}",
            "P&L": "{:+,.2f}",
            "P&L %": "{:+.2f}%",
        }),
        use_container_width=True,
        hide_index=True,
    )


render()
