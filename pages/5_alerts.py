"""Page 5: Alerts & Notifications — Config, history, acknowledge, summary."""

import pandas as pd
import streamlit as st

from config.settings import ALERT_TYPES, FX_PAIRS, SEVERITY_COLORS, THEME_ETFS, THEME_TICKER_GROUPS
from data.database import (
    acknowledge_alert, add_alert_config, delete_alert_config,
    get_alert_configs, get_alert_history, get_positions,
    seed_default_alerts, update_alert_config,
)


# Alert types that need specific ticker sets (not portfolio positions)
_THEME_TICKER_TYPES = {"sector_rotation"}
_FX_TICKER_TYPES = {"currency_risk"}
_CONCENTRATION_TICKER_TYPES = {"concentration_risk"}
_PORTFOLIO_LEVEL_TYPES = {
    "total_loss", "vix_spike", "correlation_spike",
    "market_regime_change", "morningstar_downgrade",
}


def render():
    st.header("Alerts & Notifications")
    st.caption("Your automatic watchdog — it checks your investments and warns you when something needs attention.")

    # Summary metrics row
    all_history = get_alert_history(limit=200)
    configs = get_alert_configs()
    active_count = len(configs[configs["enabled"] == 1]) if not configs.empty else 0

    unack = all_history[all_history["acknowledged"] == 0] if not all_history.empty else pd.DataFrame()
    today_str = pd.Timestamp.now().strftime("%Y-%m-%d")
    today_alerts = all_history[
        all_history["triggered_at"].str.startswith(today_str)
    ] if not all_history.empty else pd.DataFrame()

    last_alert = all_history.iloc[0]["triggered_at"] if not all_history.empty else "Never"

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("Rules Watching", active_count, help="How many automatic checks are running for you")
    with col_m2:
        st.metric("Need Attention", len(unack), help="Alerts you haven't reviewed yet")
    with col_m3:
        st.metric("Alerts Today", len(today_alerts))
    with col_m4:
        st.metric("Last Alert", str(last_alert)[:16] if last_alert != "Never" else "Never")

    st.divider()

    tab_active, tab_history, tab_config = st.tabs([
        "Active Alerts", "Alert History", "Configure"
    ])

    # --- Active Alerts ---
    with tab_active:
        alerts = get_alert_history(limit=50, unacknowledged_only=True)
        if alerts.empty:
            st.success("Everything looks good — no warnings right now")
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

        # Seed button
        if configs.empty:
            st.info("You have no alert rules yet. Click below to set up 34 recommended rules that will watch your portfolio automatically.")
            if st.button("Set Up Recommended Alerts (34 rules)", type="primary"):
                seed_default_alerts()
                st.success("Done! 34 alert rules are now watching your portfolio.")
                st.rerun()

        if not configs.empty:
            for _, cfg in configs.iterrows():
                with st.expander(
                    f"{'🟢' if cfg['enabled'] else '🔴'} "
                    f"{cfg['alert_type']} — {cfg.get('ticker') or 'Portfolio'} "
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

        with st.form("add_alert_form"):
            col1, col2 = st.columns(2)
            with col1:
                alert_type = st.selectbox("Alert Type", list(ALERT_TYPES.keys()))
                st.caption(ALERT_TYPES.get(alert_type, ""))

                # Smart ticker selection based on alert type
                if alert_type in _PORTFOLIO_LEVEL_TYPES:
                    ticker = "(Portfolio-level)"
                    st.text("Portfolio-level alert (no ticker needed)")
                elif alert_type in _THEME_TICKER_TYPES:
                    theme_options = list(THEME_ETFS.values())
                    ticker = st.selectbox("Theme ETF", theme_options)
                elif alert_type in _FX_TICKER_TYPES:
                    fx_options = list(FX_PAIRS.keys())
                    ticker = st.selectbox("FX Pair", fx_options)
                elif alert_type in _CONCENTRATION_TICKER_TYPES:
                    theme_options = list(THEME_TICKER_GROUPS.keys())
                    ticker = st.selectbox("Theme Group", theme_options)
                else:
                    ticker_options = ["(Portfolio-level)"] + (
                        positions["ticker"].tolist() if not positions.empty else []
                    )
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
