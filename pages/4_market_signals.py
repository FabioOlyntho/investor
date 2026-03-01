"""Page 4: Market Signals — VIX, yield curve, sector momentum, regime gauge."""

import streamlit as st

from components.charts import (
    regime_gauge, sector_momentum_bar, vix_chart, yield_curve_chart,
)
from data.calculations import market_regime_score
from data.market_data import (
    fetch_sector_performance, fetch_vix,
    fetch_yield_curve, fetch_yield_curve_historical,
)


def render():
    st.header("Market Signals")

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

    # Layout
    col1, col2 = st.columns([1, 2])

    with col1:
        # Regime gauge
        fig = regime_gauge(regime)
        st.plotly_chart(fig, use_container_width=True)

        label = "Risk-Off" if regime < 33 else ("Neutral" if regime < 66 else "Risk-On")
        color = "#FF1744" if regime < 33 else ("#FFD600" if regime < 66 else "#00C853")
        st.markdown(
            f"<h3 style='text-align:center;color:{color}'>{label}</h3>",
            unsafe_allow_html=True,
        )

        if current_vix is not None:
            st.metric("VIX", f"{current_vix:.1f}")
        if yield_spread is not None:
            st.metric("10Y-2Y Spread", f"{yield_spread:.2f}%")
        if momentum_positive is not None:
            st.metric("Sectors Positive", f"{momentum_positive*100:.0f}%")

    with col2:
        # VIX chart
        fig = vix_chart(vix_data)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    col3, col4 = st.columns(2)

    with col3:
        # Yield curve
        if yields_current:
            fig = yield_curve_chart(yields_current, yields_hist)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Could not fetch yield data.")

    with col4:
        # Sector momentum
        if sector_perf:
            fig = sector_momentum_bar(sector_perf)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Could not fetch sector data.")


render()
