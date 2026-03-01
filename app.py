"""InvestmentMonitor — Streamlit entrypoint."""

import streamlit as st

from data.database import init_db

# Initialize database on first run
init_db()

# Page config
st.set_page_config(
    page_title="InvestmentMonitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Navigation
pages = {
    "Portfolio": [
        st.Page("pages/1_portfolio_overview.py", title="Overview", icon="📊", default=True),
        st.Page("pages/2_performance_analysis.py", title="Performance", icon="📈"),
        st.Page("pages/3_risk_analysis.py", title="Risk", icon="🛡️"),
    ],
    "Market": [
        st.Page("pages/4_market_signals.py", title="Signals", icon="📡"),
    ],
    "Settings": [
        st.Page("pages/5_alerts.py", title="Alerts", icon="🔔"),
        st.Page("pages/6_portfolio_management.py", title="Portfolio Mgmt", icon="⚙️"),
    ],
}

nav = st.navigation(pages)

# Sidebar branding
with st.sidebar:
    st.markdown(
        "<h2 style='color:#FF002A;margin-bottom:0'>InvestmentMonitor</h2>"
        "<p style='color:#78909C;font-size:12px;margin-top:0'>Portfolio Dashboard & Alerts</p>",
        unsafe_allow_html=True,
    )

nav.run()
