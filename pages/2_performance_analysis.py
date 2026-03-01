"""Page 2: Performance Analysis — Returns, benchmark, heatmap."""

import pandas as pd
import streamlit as st

from components.charts import (
    cumulative_returns_chart, monthly_heatmap,
    return_distribution_histogram, rolling_metric_chart,
)
from data.calculations import (
    annualized_return, annualized_volatility, daily_returns,
    rolling_returns, sharpe_ratio,
)
from data.database import get_positions
from data.market_data import fetch_multi_history, fetch_benchmark_history


def render():
    st.header("Performance Analysis")

    positions = get_positions()
    if positions.empty:
        st.info("No positions. Add some in Portfolio Management.")
        return

    tickers = tuple(positions["ticker"].tolist())
    unique_tickers = tuple(dict.fromkeys(tickers))

    # Sidebar filters
    with st.sidebar:
        st.subheader("Filters")
        period = st.selectbox("Period", ["3mo", "6mo", "1y", "2y", "5y", "max"], index=2)
        rolling_window = st.slider("Rolling Window (days)", 10, 90, 30)

    hist = fetch_multi_history(unique_tickers, period=period)
    if hist.empty or len(hist) < 5:
        st.warning("Not enough price history. Try a different period or check tickers.")
        return

    # Build weighted portfolio returns
    available = [t for t in unique_tickers if t in hist.columns]
    if not available:
        st.warning("No matching price data found.")
        return

    # Weight by cost basis
    weights = {}
    for _, pos in positions.iterrows():
        if pos["ticker"] in available:
            weights[pos["ticker"]] = weights.get(pos["ticker"], 0) + pos["cost_basis"]
    total_w = sum(weights.values())
    if total_w == 0:
        st.warning("Total cost basis is 0.")
        return

    w = pd.Series({t: weights.get(t, 0) / total_w for t in available})
    returns_df = hist[available].ffill().pct_change().fillna(0)
    port_returns = (returns_df * w).sum(axis=1)

    # Benchmark
    bench = fetch_benchmark_history(period=period)
    bench_returns = None
    if not bench.empty:
        bench_returns = daily_returns(bench["Close"])
        bench_returns = bench_returns.reindex(port_returns.index).dropna()

    # Key metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Ann. Return", f"{annualized_return(port_returns)*100:.2f}%")
    with c2:
        st.metric("Ann. Volatility", f"{annualized_volatility(port_returns)*100:.2f}%")
    with c3:
        st.metric("Sharpe Ratio", f"{sharpe_ratio(port_returns):.2f}")
    with c4:
        total_ret = ((1 + port_returns).prod() - 1) * 100
        st.metric("Total Return", f"{total_ret:+.2f}%")

    st.divider()

    # Cumulative returns
    fig = cumulative_returns_chart(port_returns, bench_returns)
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        # Monthly heatmap
        fig = monthly_heatmap(port_returns)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Return distribution
        fig = return_distribution_histogram(port_returns)
        st.plotly_chart(fig, use_container_width=True)

    # Rolling return
    roll = rolling_returns(port_returns, window=rolling_window)
    fig = rolling_metric_chart(
        roll * 100,
        title=f"Rolling {rolling_window}-Day Return",
        ylabel="Return (%)"
    )
    st.plotly_chart(fig, use_container_width=True)


render()
