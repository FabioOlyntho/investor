"""Reusable Plotly chart builders."""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from config.settings import (
    CHART_COLORS, POSITIVE_COLOR, NEGATIVE_COLOR, NEUTRAL_COLOR,
    PRIMARY_COLOR, SECTOR_COLORS, SEVERITY_COLORS,
)

_LAYOUT_DEFAULTS = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=40, b=40),
    font=dict(color="#FAFAFA", size=12),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        borderwidth=0,
    ),
    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
    yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
)


def _apply_layout(fig: go.Figure, title: str = "", height: int = 400) -> go.Figure:
    fig.update_layout(**_LAYOUT_DEFAULTS, title=title, height=height)
    return fig


def portfolio_value_chart(
    dates: pd.DatetimeIndex,
    values: pd.Series,
    benchmark: pd.Series = None,
    benchmarks: dict[str, pd.Series] = None,
    title: str = "Portfolio Value",
) -> go.Figure:
    """Line chart with fill for portfolio value over time.

    Args:
        benchmarks: dict of {name: series} for multiple comparison lines.
        benchmark: single benchmark series (legacy, used if benchmarks is None).
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=values, name="Your Portfolio",
        fill="tozeroy", fillcolor="rgba(255,0,42,0.1)",
        line=dict(color=PRIMARY_COLOR, width=2),
    ))
    if benchmarks:
        bench_colors = ["#2979FF", "#FF9100", "#AA00FF", "#00BFA5"]
        for i, (name, series) in enumerate(benchmarks.items()):
            if series is not None and not series.empty:
                fig.add_trace(go.Scatter(
                    x=dates, y=series, name=name,
                    line=dict(color=bench_colors[i % len(bench_colors)], width=1, dash="dash"),
                ))
    elif benchmark is not None and not benchmark.empty:
        fig.add_trace(go.Scatter(
            x=dates, y=benchmark, name="Benchmark",
            line=dict(color=NEUTRAL_COLOR, width=1, dash="dash"),
        ))
    return _apply_layout(fig, title)


def allocation_donut(
    labels: list[str], values: list[float], title: str = "Asset Allocation"
) -> go.Figure:
    """Donut pie chart for allocation."""
    colors = [SECTOR_COLORS.get(l, CHART_COLORS[i % len(CHART_COLORS)])
              for i, l in enumerate(labels)]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.55, marker=dict(colors=colors),
        textinfo="label+percent", textposition="outside",
        hovertemplate="%{label}: %{value:,.0f} (%{percent})<extra></extra>",
    ))
    return _apply_layout(fig, title, height=380)


def pnl_bar_chart(
    tickers: list[str], pnl_values: list[float],
    title: str = "P&L per Position"
) -> go.Figure:
    """Horizontal bar chart for P&L, green for gains, red for losses."""
    colors = [POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in pnl_values]
    fig = go.Figure(go.Bar(
        x=pnl_values, y=tickers, orientation="h",
        marker_color=colors,
        hovertemplate="%{y}: %{x:,.2f}<extra></extra>",
    ))
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return _apply_layout(fig, title)


def sector_exposure_bar(
    sectors: list[str], weights: list[float],
    title: str = "Sector Exposure"
) -> go.Figure:
    """Horizontal stacked bar for sector weights."""
    colors = [SECTOR_COLORS.get(s, CHART_COLORS[i % len(CHART_COLORS)])
              for i, s in enumerate(sectors)]
    fig = go.Figure(go.Bar(
        x=weights, y=["Portfolio"] * len(sectors),
        orientation="h",
        marker_color=colors,
        text=[f"{s} ({w:.1f}%)" for s, w in zip(sectors, weights)],
        textposition="inside",
        hovertemplate="%{text}<extra></extra>",
    ))
    fig.update_layout(barmode="stack", showlegend=False)
    return _apply_layout(fig, title, height=160)


def cumulative_returns_chart(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series = None,
    title: str = "Cumulative Returns",
) -> go.Figure:
    """Line chart comparing cumulative returns."""
    fig = go.Figure()
    cum_port = (1 + portfolio_returns).cumprod() - 1
    fig.add_trace(go.Scatter(
        x=cum_port.index, y=cum_port.values * 100,
        name="Portfolio", line=dict(color=PRIMARY_COLOR, width=2),
    ))
    if benchmark_returns is not None and not benchmark_returns.empty:
        cum_bench = (1 + benchmark_returns).cumprod() - 1
        fig.add_trace(go.Scatter(
            x=cum_bench.index, y=cum_bench.values * 100,
            name="Benchmark", line=dict(color=NEUTRAL_COLOR, width=1, dash="dash"),
        ))
    fig.update_layout(yaxis_title="Return (%)")
    return _apply_layout(fig, title)


def monthly_heatmap(returns: pd.Series, title: str = "Monthly Returns") -> go.Figure:
    """Calendar-grid heatmap of monthly returns."""
    if returns.empty:
        return _apply_layout(go.Figure(), title)

    monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly.index = monthly.index.to_period("M")

    years = sorted(set(monthly.index.year))
    months = list(range(1, 13))
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    z = []
    for year in years:
        row = []
        for month in months:
            period = pd.Period(year=year, month=month, freq="M")
            val = monthly.get(period)
            row.append(val * 100 if val is not None and not pd.isna(val) else None)
        z.append(row)

    fig = go.Figure(go.Heatmap(
        z=z, x=month_labels, y=[str(y) for y in years],
        colorscale="RdYlGn", zmid=0,
        text=[[f"{v:.1f}%" if v is not None else "" for v in row] for row in z],
        texttemplate="%{text}",
        hovertemplate="Year %{y}, %{x}: %{z:.2f}%<extra></extra>",
    ))
    return _apply_layout(fig, title, height=max(200, len(years) * 50 + 80))


def drawdown_chart(drawdown: pd.Series, title: str = "Drawdown from Peak") -> go.Figure:
    """Area chart for drawdown series."""
    fig = go.Figure(go.Scatter(
        x=drawdown.index, y=drawdown.values * 100,
        fill="tozeroy", fillcolor="rgba(255,23,68,0.2)",
        line=dict(color=NEGATIVE_COLOR, width=1.5),
        hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(yaxis_title="Drawdown (%)")
    return _apply_layout(fig, title)


def correlation_heatmap(
    corr_matrix: pd.DataFrame, title: str = "Correlation Matrix"
) -> go.Figure:
    """Heatmap for position correlations."""
    fig = go.Figure(go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns.tolist(),
        y=corr_matrix.index.tolist(),
        colorscale="RdBu", zmid=0,
        text=[[f"{v:.2f}" for v in row] for row in corr_matrix.values],
        texttemplate="%{text}",
        hovertemplate="%{x} vs %{y}: %{z:.3f}<extra></extra>",
    ))
    return _apply_layout(fig, title, height=max(350, len(corr_matrix) * 35 + 80))


def risk_return_scatter(
    tickers: list[str],
    returns_ann: list[float],
    vol_ann: list[float],
    market_values: list[float],
    title: str = "Risk/Return",
) -> go.Figure:
    """Scatter plot with position as dot, size = market value."""
    max_mv = max(market_values) if market_values else 1
    sizes = [max(10, (mv / max_mv) * 50) for mv in market_values]
    fig = go.Figure(go.Scatter(
        x=vol_ann, y=returns_ann, mode="markers+text",
        marker=dict(size=sizes, color=CHART_COLORS[:len(tickers)], opacity=0.8),
        text=tickers, textposition="top center",
        hovertemplate="%{text}<br>Return: %{y:.1f}%<br>Vol: %{x:.1f}%<extra></extra>",
    ))
    fig.update_layout(xaxis_title="Volatility (Ann. %)", yaxis_title="Return (Ann. %)")
    return _apply_layout(fig, title)


def vix_chart(vix_data: pd.DataFrame, title: str = "VIX Index") -> go.Figure:
    """VIX time series with colored zones."""
    fig = go.Figure()
    if vix_data.empty:
        return _apply_layout(fig, title)

    dates = vix_data.index
    close = vix_data["Close"]

    # Colored zones
    fig.add_hrect(y0=0, y1=15, fillcolor="rgba(0,200,83,0.08)", line_width=0)
    fig.add_hrect(y0=15, y1=25, fillcolor="rgba(255,214,0,0.08)", line_width=0)
    fig.add_hrect(y0=25, y1=80, fillcolor="rgba(255,23,68,0.08)", line_width=0)

    fig.add_trace(go.Scatter(
        x=dates, y=close, line=dict(color=PRIMARY_COLOR, width=2),
        hovertemplate="%{x}: %{y:.1f}<extra></extra>",
    ))

    fig.add_hline(y=15, line_dash="dot", line_color=POSITIVE_COLOR, opacity=0.5)
    fig.add_hline(y=25, line_dash="dot", line_color=NEGATIVE_COLOR, opacity=0.5)

    return _apply_layout(fig, title)


def yield_curve_chart(
    current: dict[str, float],
    historical: dict[str, float] = None,
    title: str = "US Treasury Yield Curve",
) -> go.Figure:
    """Yield curve snapshot with optional historical comparison."""
    fig = go.Figure()
    maturities = list(current.keys())
    fig.add_trace(go.Scatter(
        x=maturities, y=list(current.values()),
        name="Current", line=dict(color=PRIMARY_COLOR, width=2),
        mode="lines+markers",
    ))
    if historical:
        fig.add_trace(go.Scatter(
            x=maturities, y=[historical.get(m, None) for m in maturities],
            name="3M Ago", line=dict(color=NEUTRAL_COLOR, width=1, dash="dash"),
            mode="lines+markers",
        ))
    fig.update_layout(yaxis_title="Yield (%)")
    return _apply_layout(fig, title, height=350)


def sector_momentum_bar(
    sectors: dict[str, float], title: str = "Sector Momentum (1M Return)"
) -> go.Figure:
    """Horizontal bar sorted by return."""
    sorted_items = sorted(sectors.items(), key=lambda x: x[1])
    names = [s[0] for s in sorted_items]
    vals = [s[1] for s in sorted_items]
    colors = [POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in vals]

    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h",
        marker_color=colors,
        hovertemplate="%{y}: %{x:.2f}%<extra></extra>",
    ))
    fig.update_layout(xaxis_title="Return (%)")
    return _apply_layout(fig, title, height=max(300, len(names) * 30 + 80))


def regime_gauge(score: float, title: str = "Market Regime") -> go.Figure:
    """Gauge chart 0-100 with traffic light coloring."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title=dict(text=title, font=dict(size=16)),
        number=dict(font=dict(size=36)),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1),
            bar=dict(color=PRIMARY_COLOR),
            steps=[
                dict(range=[0, 33], color="rgba(255,23,68,0.3)"),
                dict(range=[33, 66], color="rgba(255,214,0,0.3)"),
                dict(range=[66, 100], color="rgba(0,200,83,0.3)"),
            ],
            threshold=dict(
                line=dict(color="white", width=2),
                thickness=0.75, value=score
            ),
        ),
    ))
    return _apply_layout(fig, "", height=280)


def return_distribution_histogram(
    returns: pd.Series, title: str = "Return Distribution"
) -> go.Figure:
    """Histogram of daily returns."""
    fig = go.Figure(go.Histogram(
        x=returns.values * 100,
        nbinsx=50,
        marker_color=PRIMARY_COLOR,
        opacity=0.7,
        hovertemplate="Return: %{x:.2f}%<br>Count: %{y}<extra></extra>",
    ))
    fig.add_vline(x=0, line_dash="dash", line_color="white", opacity=0.5)
    fig.update_layout(xaxis_title="Daily Return (%)", yaxis_title="Frequency")
    return _apply_layout(fig, title, height=350)


def rolling_metric_chart(
    series: pd.Series, title: str = "", ylabel: str = ""
) -> go.Figure:
    """Generic rolling metric line chart."""
    fig = go.Figure(go.Scatter(
        x=series.index, y=series.values,
        line=dict(color=PRIMARY_COLOR, width=1.5),
        hovertemplate="%{x}: %{y:.2f}<extra></extra>",
    ))
    fig.update_layout(yaxis_title=ylabel)
    return _apply_layout(fig, title)


def theme_momentum_bar(
    theme_perf: dict[str, float],
    theme_etfs: dict[str, str],
    title: str = "Theme Momentum (1M Return)",
) -> go.Figure:
    """Horizontal bar chart for theme ETF performance.

    Args:
        theme_perf: {ticker: return_pct} e.g. {"EWY": -3.2}
        theme_etfs: {theme_name: ticker} e.g. {"Korea": "EWY"}
    """
    # Build label → return mapping using theme names
    etf_to_theme = {v: k for k, v in theme_etfs.items()}
    items = []
    for ticker, ret in theme_perf.items():
        label = etf_to_theme.get(ticker, ticker)
        items.append((label, ret))
    items.sort(key=lambda x: x[1])

    names = [i[0] for i in items]
    vals = [i[1] for i in items]
    colors = [POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in vals]

    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h",
        marker_color=colors,
        hovertemplate="%{y}: %{x:.2f}%<extra></extra>",
    ))
    fig.update_layout(xaxis_title="Return (%)")
    return _apply_layout(fig, title, height=max(250, len(names) * 35 + 80))


def treemap_chart(
    labels: list[str], parents: list[str], values: list[float],
    title: str = "Risk Contribution"
) -> go.Figure:
    """Treemap for hierarchical data."""
    fig = go.Figure(go.Treemap(
        labels=labels, parents=parents, values=values,
        marker=dict(colorscale="RdYlGn"),
        hovertemplate="%{label}: %{value:.2f}%<extra></extra>",
    ))
    return _apply_layout(fig, title, height=400)
