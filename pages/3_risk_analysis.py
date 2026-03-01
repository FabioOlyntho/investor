"""Page 3: Risk Analysis — Volatility, drawdown, correlation, VaR."""

import numpy as np
import pandas as pd
import streamlit as st

from components.charts import (
    correlation_heatmap, drawdown_chart, risk_return_scatter,
    rolling_metric_chart,
)
from components.metrics import risk_metrics_row
from data.calculations import (
    annualized_return, annualized_volatility, beta,
    correlation_matrix, daily_returns, drawdown_series,
    max_drawdown, rolling_volatility, value_at_risk,
)
from data.database import get_positions
from data.market_data import fetch_current_prices, fetch_multi_history, fetch_benchmark_history


def render():
    st.header("Risk Analysis")

    positions = get_positions()
    if positions.empty:
        st.info("No positions. Add some in Portfolio Management.")
        return

    tickers = tuple(positions["ticker"].tolist())
    period = st.sidebar.selectbox("Period", ["6mo", "1y", "2y", "5y"], index=1, key="risk_period")

    hist = fetch_multi_history(tickers, period=period)
    if hist.empty or len(hist) < 20:
        st.warning("Not enough data for risk analysis.")
        return

    available = [t for t in tickers if t in hist.columns]
    if not available:
        st.warning("No matching price data.")
        return

    # Weighted portfolio
    weights = {}
    for _, pos in positions.iterrows():
        if pos["ticker"] in available:
            weights[pos["ticker"]] = pos["cost_basis"]
    total_w = sum(weights.values())
    if total_w == 0:
        return

    w = pd.Series({t: weights.get(t, 0) / total_w for t in available})
    returns_df = hist[available].pct_change().dropna()
    port_returns = (returns_df * w).sum(axis=1)
    port_prices = (1 + port_returns).cumprod()

    # Benchmark
    bench = fetch_benchmark_history(period=period)
    bench_returns = None
    port_beta = None
    if not bench.empty:
        bench_returns = daily_returns(bench["Close"])
        bench_returns = bench_returns.reindex(port_returns.index).dropna()
        if len(bench_returns) > 10:
            port_beta = beta(port_returns, bench_returns)

    # Metrics row
    vol = annualized_volatility(port_returns) * 100
    mdd = max_drawdown(port_prices) * 100
    var95 = value_at_risk(port_returns) * 100

    risk_metrics_row(
        volatility=vol,
        max_drawdown=mdd,
        var_95=var95,
        beta=port_beta,
    )

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        # Risk/Return scatter
        prices_data = fetch_current_prices(tickers)
        rets_ann = []
        vols_ann = []
        mvs = []
        scatter_tickers = []
        for t in available:
            if t in returns_df.columns:
                r = returns_df[t].dropna()
                rets_ann.append(annualized_return(r) * 100)
                vols_ann.append(annualized_volatility(r) * 100)
                pos_row = positions[positions["ticker"] == t].iloc[0]
                price = prices_data.get(t, {}).get("price", 0)
                mvs.append(pos_row["units"] * price)
                scatter_tickers.append(t)

        fig = risk_return_scatter(scatter_tickers, rets_ann, vols_ann, mvs)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Correlation heatmap
        if len(available) >= 2:
            corr = correlation_matrix(hist[available])
            fig = correlation_heatmap(corr)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Need at least 2 positions for correlation analysis.")

    # Drawdown chart
    dd = drawdown_series(port_prices)
    fig = drawdown_chart(dd)
    st.plotly_chart(fig, use_container_width=True)

    # Rolling volatility
    roll_vol = rolling_volatility(port_returns, window=30) * 100
    fig = rolling_metric_chart(
        roll_vol,
        title="Rolling 30-Day Volatility (Ann.)",
        ylabel="Volatility (%)"
    )
    st.plotly_chart(fig, use_container_width=True)


render()
