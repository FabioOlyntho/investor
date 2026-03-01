"""Streamlit metric card helpers."""

import streamlit as st

from components.formatters import fmt_currency, fmt_percent


def portfolio_metrics_row(
    total_value: float,
    daily_change: float,
    daily_change_pct: float,
    total_pnl: float,
    total_pnl_pct: float,
    sharpe: float = None,
):
    """Render 4 top-level metric cards in columns."""
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Total Value",
            fmt_currency(total_value),
            delta=fmt_percent(daily_change_pct),
        )
    with c2:
        st.metric(
            "Daily Change",
            fmt_currency(daily_change),
            delta=fmt_percent(daily_change_pct),
        )
    with c3:
        st.metric(
            "Total P&L",
            fmt_currency(total_pnl),
            delta=fmt_percent(total_pnl_pct),
        )
    with c4:
        sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "N/A"
        st.metric("Sharpe Ratio", sharpe_str)


def risk_metrics_row(
    volatility: float,
    max_drawdown: float,
    var_95: float,
    beta: float,
):
    """Render 4 risk metric cards."""
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Volatility (Ann.)", fmt_percent(volatility))
    with c2:
        st.metric("Max Drawdown", fmt_percent(max_drawdown))
    with c3:
        st.metric("VaR 95%", fmt_percent(var_95))
    with c4:
        st.metric("Beta", f"{beta:.2f}" if beta is not None else "N/A")
