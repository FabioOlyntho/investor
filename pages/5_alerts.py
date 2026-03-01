"""Page 5: Alerts & Notifications — Config, history, acknowledge."""

import pandas as pd
import streamlit as st

from config.settings import ALERT_TYPES, SEVERITY_COLORS
from data.database import (
    acknowledge_alert, add_alert_config, delete_alert_config,
    get_alert_configs, get_alert_history, get_positions,
    update_alert_config,
)


def render():
    st.header("Alerts & Notifications")

    tab_active, tab_history, tab_config = st.tabs([
        "Active Alerts", "Alert History", "Configure"
    ])

    # --- Active Alerts ---
    with tab_active:
        alerts = get_alert_history(limit=50, unacknowledged_only=True)
        if alerts.empty:
            st.success("No active alerts")
        else:
            st.caption(f"{len(alerts)} unacknowledged alert(s)")
            for _, alert in alerts.iterrows():
                severity = alert["severity"]
                color = SEVERITY_COLORS.get(severity, "#78909C")
                with st.container():
                    col1, col2, col3 = st.columns([1, 6, 1])
                    with col1:
                        st.markdown(
                            f"<span style='color:{color};font-size:24px'>●</span>",
                            unsafe_allow_html=True,
                        )
                    with col2:
                        st.markdown(f"**{alert['message']}**")
                        st.caption(f"{alert['triggered_at']} — {severity.upper()}")
                    with col3:
                        if st.button("Ack", key=f"ack_{alert['id']}"):
                            acknowledge_alert(int(alert["id"]))
                            st.rerun()
                    st.divider()

    # --- Alert History ---
    with tab_history:
        history = get_alert_history(limit=100)
        if history.empty:
            st.info("No alert history yet.")
        else:
            display = history[["triggered_at", "severity", "message", "acknowledged"]].copy()
            display["acknowledged"] = display["acknowledged"].map({0: "No", 1: "Yes"})
            display.columns = ["Time", "Severity", "Message", "Ack"]
            st.dataframe(
                display.style.applymap(
                    lambda v: f"color: {SEVERITY_COLORS.get(v.lower(), '')}"
                    if isinstance(v, str) and v.lower() in SEVERITY_COLORS else "",
                    subset=["Severity"]
                ),
                use_container_width=True,
                hide_index=True,
            )

    # --- Configure ---
    with tab_config:
        st.subheader("Alert Rules")

        configs = get_alert_configs()
        if not configs.empty:
            for _, cfg in configs.iterrows():
                with st.expander(
                    f"{'🟢' if cfg['enabled'] else '🔴'} "
                    f"{cfg['alert_type']} — {cfg.get('ticker', 'Portfolio')} "
                    f"({cfg['severity']})"
                ):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.text(ALERT_TYPES.get(cfg["alert_type"], ""))
                        st.text(f"Threshold: {cfg['threshold']} ({cfg['direction']})")
                    with col2:
                        enabled = st.toggle(
                            "Enabled", value=bool(cfg["enabled"]),
                            key=f"toggle_{cfg['id']}"
                        )
                        if enabled != bool(cfg["enabled"]):
                            update_alert_config(int(cfg["id"]), enabled=int(enabled))
                            st.rerun()
                    with col3:
                        if st.button("Delete", key=f"del_cfg_{cfg['id']}"):
                            delete_alert_config(int(cfg["id"]))
                            st.rerun()

        st.divider()
        st.subheader("Add Alert Rule")

        positions = get_positions()
        ticker_options = ["(Portfolio-level)"] + (
            positions["ticker"].tolist() if not positions.empty else []
        )

        with st.form("add_alert_form"):
            col1, col2 = st.columns(2)
            with col1:
                alert_type = st.selectbox("Alert Type", list(ALERT_TYPES.keys()))
                st.caption(ALERT_TYPES.get(alert_type, ""))
                ticker = st.selectbox("Ticker", ticker_options)
            with col2:
                threshold = st.number_input("Threshold", step=0.1, format="%.2f")
                direction = st.selectbox("Direction", ["below", "above"])
                severity = st.selectbox("Severity", ["critical", "warning", "info"])

            if st.form_submit_button("Add Rule", type="primary"):
                tk = ticker if ticker != "(Portfolio-level)" else None
                add_alert_config(
                    alert_type=alert_type,
                    threshold=threshold,
                    direction=direction,
                    severity=severity,
                    ticker=tk,
                )
                st.success(f"Added {alert_type} alert rule")
                st.rerun()


render()
