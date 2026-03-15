"""InvestmentMonitor — Streamlit entrypoint."""

from dotenv import load_dotenv
load_dotenv(override=True)

import streamlit as st

from data.database import init_db

# Initialize database on first run
init_db()

# Page config
st.set_page_config(
    page_title="InvestmentMonitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Navigation — single dashboard + settings pages
pages = {
    "Dashboard": [
        st.Page("pages/1_dashboard.py", title="Dashboard", icon="📊", default=True),
        st.Page("pages/7_advisor.py", title="AI Advisor", icon="🤖"),
    ],
    "Settings": [
        st.Page("pages/5_alerts.py", title="Alert Rules", icon="🔔"),
        st.Page("pages/6_portfolio_management.py", title="Portfolio Management", icon="⚙️"),
    ],
}

nav = st.navigation(pages)

# Sidebar branding
with st.sidebar:
    st.markdown(
        "<h2 style='color:#FF002A;margin-bottom:0'>InvestmentMonitor</h2>"
        "<p style='color:#78909C;font-size:12px;margin-top:0'>Your Investment Dashboard</p>",
        unsafe_allow_html=True,
    )

nav.run()
