"""AI Financial Advisor page — daily analysis, rebalancing, opportunities, Q&A."""

import streamlit as st

from config.settings import PRIMARY_COLOR, POSITIVE_COLOR, NEGATIVE_COLOR

st.header("AI Financial Advisor")
st.caption("AI-powered portfolio analysis and recommendations. "
           "This is informational analysis, not financial advice.")

tab_daily, tab_rebalance, tab_opportunities, tab_qa = st.tabs([
    "Daily Analysis", "Rebalancing", "Opportunities", "Ask Your Advisor",
])


def _render_analysis(result: dict, label: str):
    """Render an AI analysis result with metadata."""
    if result.get("cached"):
        created = result.get("created_at", "")
        date_str = created[:16].replace("T", " ") if created else "unknown date"
        st.info(f"Showing cached {label} — generated on {date_str}. "
                f"Click **Refresh** to update.")
    elif result.get("model"):
        st.caption(f"Generated just now by {result['provider']}/{result['model']}")
    st.markdown(result["text"])


# --- Tab 1: Daily Analysis ---
with tab_daily:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Today's Briefing")
    with col2:
        refresh_daily = st.button("Refresh", key="refresh_daily")

    with st.spinner("Generating daily analysis..."):
        try:
            from data.advisor_engine import generate_daily_analysis
            result = generate_daily_analysis(force_refresh=refresh_daily)
            _render_analysis(result, "daily analysis")
        except Exception as e:
            st.error(f"Could not generate daily analysis: {e}")
            st.info("Make sure an LLM API key is configured "
                    "(GOOGLE_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY).")


# --- Tab 2: Rebalancing ---
with tab_rebalance:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Portfolio Rebalancing")
    with col2:
        refresh_rebal = st.button("Refresh", key="refresh_rebalance")

    with st.spinner("Analyzing portfolio allocation..."):
        try:
            from data.advisor_engine import generate_rebalance_analysis
            result = generate_rebalance_analysis(force_refresh=refresh_rebal)
            _render_analysis(result, "rebalancing analysis")
        except Exception as e:
            st.error(f"Could not generate rebalancing analysis: {e}")


# --- Tab 3: Opportunities ---
with tab_opportunities:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Investment Opportunities")
    with col2:
        refresh_opp = st.button("Refresh", key="refresh_opportunities")

    with st.spinner("Scanning for opportunities..."):
        try:
            from data.advisor_engine import generate_opportunity_scan
            result = generate_opportunity_scan(force_refresh=refresh_opp)
            _render_analysis(result, "opportunity scan")
        except Exception as e:
            st.error(f"Could not scan for opportunities: {e}")



# --- Tab 4: Ask Your Advisor ---
with tab_qa:
    st.subheader("Ask a Question")
    st.caption("Ask about your portfolio, market conditions, or specific positions. "
               "Your question will be answered using your actual portfolio data.")

    # Initialize chat history
    if "advisor_messages" not in st.session_state:
        st.session_state.advisor_messages = []

    # Display chat history
    for msg in st.session_state.advisor_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if question := st.chat_input("e.g. Should I reduce my Korea exposure?"):
        # Show user message
        st.session_state.advisor_messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    from data.advisor_engine import ask_advisor
                    result = ask_advisor(question)
                    st.markdown(result["text"])
                    if result.get("model"):
                        st.caption(f"— {result['provider']}/{result['model']}")
                    st.session_state.advisor_messages.append(
                        {"role": "assistant", "content": result["text"]}
                    )
                except Exception as e:
                    error_msg = f"Could not get a response: {e}"
                    st.error(error_msg)
                    st.session_state.advisor_messages.append(
                        {"role": "assistant", "content": error_msg}
                    )
