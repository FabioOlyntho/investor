"""CLI script for n8n cron — comprehensive daily briefing + alert evaluation.

Usage:
    python -m cli.daily_update

Always outputs JSON with full briefing HTML (not just when alerts fire).
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import pandas as pd
import yfinance as yf

from config.settings import (
    ALERT_EMAIL, BENCHMARK_INDICES, CURRENCY_OVERRIDES, FX_PAIRS,
    PRICE_SCALE_FACTORS, PRIMARY_COLOR, SEVERITY_COLORS,
    THEME_ETFS, THEME_TICKER_GROUPS,
)
from data.calculations import market_regime_score
from data.database import (
    get_positions, init_db, save_regime_score, seed_default_alerts,
)
from data.alerts_engine import run_alert_evaluation
from data.market_data import (
    convert_to_eur,
    fetch_benchmark_indices_no_cache,
    fetch_fx_daily_changes_no_cache,
    fetch_morningstar_ratings_no_cache,
    fetch_theme_performance_no_cache,
)


def fetch_prices_no_cache(tickers: list[str]) -> dict[str, dict]:
    """Fetch prices without Streamlit cache (for CLI use)."""
    result = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            hist = t.history(period="5d")
            if hist.empty:
                continue
            current = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) >= 2 else current

            # Apply price scale factor (e.g. wrong share class on yfinance)
            scale = PRICE_SCALE_FACTORS.get(ticker, 1.0)
            current *= scale
            prev *= scale

            change = current - prev
            change_pct = (change / prev * 100) if prev != 0 else 0.0

            currency = getattr(info, "currency", None)
            currency = CURRENCY_OVERRIDES.get(ticker, currency) or "EUR"

            result[ticker] = {
                "price": current,
                "change": change,
                "change_pct": change_pct,
                "currency": currency,
            }
        except Exception:
            continue
    return result


def fetch_history_no_cache(tickers: list[str], period: str = "3mo") -> pd.DataFrame:
    """Fetch multi-ticker history without Streamlit cache."""
    try:
        data = yf.download(tickers, period=period, group_by="ticker", progress=False)
        if data.empty:
            return pd.DataFrame()
        closes = pd.DataFrame()
        if len(tickers) == 1:
            closes[tickers[0]] = data["Close"]
        else:
            for t in tickers:
                if t in data.columns.get_level_values(0):
                    closes[t] = data[t]["Close"]
        return closes.dropna(how="all")
    except Exception:
        return pd.DataFrame()


def fetch_vix_no_cache() -> pd.DataFrame:
    """Fetch VIX without Streamlit cache."""
    try:
        return yf.Ticker("^VIX").history(period="5d")
    except Exception:
        return pd.DataFrame()


def fetch_fx_rates_no_cache() -> dict[str, float]:
    """Fetch EUR FX rates without Streamlit cache."""
    rates = {"EUR": 1.0}
    fx_map = {"USD": "EURUSD=X", "GBP": "EURGBP=X", "CHF": "EURCHF=X"}
    for currency, pair in fx_map.items():
        try:
            t = yf.Ticker(pair)
            hist = t.history(period="5d")
            if not hist.empty:
                rates[currency] = 1.0 / hist["Close"].iloc[-1]
        except Exception:
            fallbacks = {"USD": 0.92, "GBP": 1.17, "CHF": 1.05}
            rates[currency] = fallbacks.get(currency, 1.0)
    rates["GBp"] = rates.get("GBP", 1.17) / 100.0
    return rates


def fetch_yield_spread_no_cache() -> float | None:
    """Fetch 10Y-2Y yield spread."""
    try:
        t10 = yf.Ticker("^TNX").history(period="5d")
        t2 = yf.Ticker("2YY=F").history(period="5d")
        if not t10.empty and not t2.empty:
            return t10["Close"].iloc[-1] - t2["Close"].iloc[-1]
    except Exception:
        pass
    return None


def build_email_html(
    alerts: list[dict],
    positions: pd.DataFrame,
    prices: dict[str, dict],
    regime_score: float,
    current_vix: float | None,
    yield_spread: float | None,
    theme_perf: dict[str, float],
    fx_changes: dict[str, dict],
    morningstar_data: list[dict],
    fx_rates: dict[str, float],
    indices: dict[str, dict] | None = None,
) -> str:
    """Build comprehensive daily briefing HTML email."""
    today = date.today().strftime("%d %B %Y")

    # Portfolio summary with EUR conversion
    total_value = 0
    total_cost = 0
    daily_pnl = 0
    movers = []
    for _, pos in positions.iterrows():
        t = pos["ticker"]
        if t not in prices:
            continue
        p = prices[t]
        currency = p.get("currency", "EUR")
        price_eur = convert_to_eur(p["price"], currency, fx_rates)
        change_eur = convert_to_eur(p["change"], currency, fx_rates)
        mv = pos["units"] * price_eur
        total_value += mv
        total_cost += pos["cost_basis"]
        day_chg = pos["units"] * change_eur
        daily_pnl += day_chg
        movers.append((pos["name"] or t, p["change_pct"], day_chg))

    pnl = total_value - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0
    daily_pnl_pct = (daily_pnl / (total_value - daily_pnl) * 100) if total_value != daily_pnl else 0

    pnl_color = "#00C853" if pnl >= 0 else "#FF1744"
    daily_color = "#00C853" if daily_pnl >= 0 else "#FF1744"

    # Regime label (plain language)
    regime_label = "Pessimistic" if regime_score < 33 else ("Mixed Feelings" if regime_score < 66 else "Optimistic")
    regime_color = "#FF1744" if regime_score < 33 else ("#FFD600" if regime_score < 66 else "#00C853")

    # Alerts section
    critical_alerts = [a for a in alerts if a["severity"] == "critical"]
    warning_alerts = [a for a in alerts if a["severity"] == "warning"]

    alert_rows = ""
    for a in critical_alerts + warning_alerts:
        color = SEVERITY_COLORS.get(a["severity"], "#78909C")
        alert_rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #333">
                <span style="color:{color};font-weight:bold">{a['severity'].upper()}</span>
            </td>
            <td style="padding:8px;border-bottom:1px solid #333">{a['message']}</td>
        </tr>"""

    # Top movers (best 3 and worst 3)
    movers.sort(key=lambda x: x[1])
    worst_3 = movers[:3]
    best_3 = movers[-3:][::-1]

    movers_html = ""
    for name, chg_pct, chg_eur in best_3 + worst_3:
        c = "#00C853" if chg_pct >= 0 else "#FF1744"
        movers_html += f"""
        <tr>
            <td style="padding:4px 8px">{name[:25]}</td>
            <td style="padding:4px 8px;text-align:right;color:{c}">{chg_pct:+.2f}%</td>
            <td style="padding:4px 8px;text-align:right;color:{c}">&euro;{chg_eur:+,.0f}</td>
        </tr>"""

    # Theme momentum
    etf_to_theme = {v: k for k, v in THEME_ETFS.items()}
    theme_html = ""
    for ticker, ret in sorted(theme_perf.items(), key=lambda x: x[1]):
        label = etf_to_theme.get(ticker, ticker)
        c = "#00C853" if ret >= 0 else "#FF1744"
        theme_html += f"""
        <tr>
            <td style="padding:4px 8px">{label}</td>
            <td style="padding:4px 8px;text-align:right;color:{c}">{ret:+.1f}%</td>
        </tr>"""

    # FX rates
    fx_html = ""
    for pair, data in fx_changes.items():
        c = "#00C853" if data["change_pct"] >= 0 else "#FF1744"
        fx_html += f"""
        <tr>
            <td style="padding:4px 8px">{pair}</td>
            <td style="padding:4px 8px;text-align:right">{data['rate']:.4f}</td>
            <td style="padding:4px 8px;text-align:right;color:{c}">{data['change_pct']:+.2f}%</td>
        </tr>"""

    # Opportunities: positions with >15% drawdown
    opportunities_html = ""
    for _, pos in positions.iterrows():
        t = pos["ticker"]
        if t not in prices:
            continue
        p = prices[t]
        currency = p.get("currency", "EUR")
        price_eur = convert_to_eur(p["price"], currency, fx_rates)
        mv = pos["units"] * price_eur
        dd_pct = ((mv - pos["cost_basis"]) / pos["cost_basis"] * 100) if pos["cost_basis"] > 0 else 0
        if dd_pct < -15:
            opportunities_html += f"""
            <tr>
                <td style="padding:4px 8px">{pos['name'] or t}</td>
                <td style="padding:4px 8px;text-align:right;color:#FF1744">{dd_pct:.1f}%</td>
            </tr>"""

    # Morningstar changes
    mstar_html = ""
    for f in morningstar_data:
        curr = f.get("star_rating")
        prev = f.get("previous_star_rating")
        if curr and prev and curr != prev:
            diff = curr - prev
            c = "#00C853" if diff > 0 else "#FF1744"
            mstar_html += f"""
            <tr>
                <td style="padding:4px 8px">{f.get('fund_name', '')[:30]}</td>
                <td style="padding:4px 8px;text-align:right">{prev}→{curr}</td>
                <td style="padding:4px 8px;text-align:right;color:{c}">{diff:+d}</td>
            </tr>"""

    # VIX zone
    vix_str = f"{current_vix:.1f}" if current_vix is not None else "N/A"
    vix_zone = "N/A"
    if current_vix is not None:
        vix_zone = "Calm (below 15)" if current_vix < 15 else ("Cautious (15-25)" if current_vix < 25 else "Scared (above 25)")

    spread_str = f"{yield_spread:.2f}%" if yield_spread is not None else "N/A"

    html = f"""
    <html>
    <body style="background:#0E1117;color:#FAFAFA;font-family:Arial,sans-serif;padding:20px">
        <div style="max-width:640px;margin:0 auto">
            <h1 style="color:{PRIMARY_COLOR}">Your Daily Investment Update</h1>
            <p style="color:#999">{today}</p>

            <!-- Portfolio Summary -->
            <div style="background:#1A1D23;padding:20px;border-radius:8px;margin:16px 0">
                <h2 style="margin-top:0">How Your Portfolio Is Doing</h2>
                <table style="width:100%">
                    <tr>
                        <td>Total Value</td>
                        <td style="text-align:right;font-weight:bold">&euro;{total_value:,.2f}</td>
                    </tr>
                    <tr>
                        <td>Today's Change</td>
                        <td style="text-align:right;color:{daily_color};font-weight:bold">
                            &euro;{daily_pnl:+,.2f} ({daily_pnl_pct:+.2f}%)
                        </td>
                    </tr>
                    <tr>
                        <td>Total Gain/Loss</td>
                        <td style="text-align:right;color:{pnl_color};font-weight:bold">
                            &euro;{pnl:+,.2f} ({pnl_pct:+.1f}%)
                        </td>
                    </tr>
                </table>
            </div>

            <!-- Market Context -->
            <div style="background:#1A1D23;padding:20px;border-radius:8px;margin:16px 0">
                <h2 style="margin-top:0">What's Happening in the Markets</h2>
                <table style="width:100%">
                    <tr>
                        <td>Market Mood</td>
                        <td style="text-align:right;color:{regime_color};font-weight:bold">
                            {regime_label} ({regime_score:.0f}/100)
                        </td>
                    </tr>
                    <tr>
                        <td>Fear Index (VIX)</td>
                        <td style="text-align:right">{vix_str} — {vix_zone}</td>
                    </tr>
                    <tr>
                        <td>Interest Rate Gap (10Y-2Y)</td>
                        <td style="text-align:right">{spread_str}</td>
                    </tr>
                </table>
                {''.join(f'<div style="display:inline-block;margin:4px 8px"><small>{p}</small>: {d["rate"]:.4f} <span style="color:{"#00C853" if d["change_pct"]>=0 else "#FF1744"}">{d["change_pct"]:+.2f}%</span></div>' for p, d in fx_changes.items())}
            </div>

            <!-- Major Indices -->
            <div style="background:#1A1D23;padding:20px;border-radius:8px;margin:16px 0">
                <h2 style="margin-top:0">Major Stock Markets</h2>
                {"".join(f'<div style="display:inline-block;margin:4px 12px"><b>{name}</b>: {data["value"]:,.0f} <span style="color:{"#00C853" if data["change_pct"]>=0 else "#FF1744"}">{data["change_pct"]:+.2f}%</span></div>' for name, data in (indices or {}).items()) or "<p style='color:#999'>Index data unavailable</p>"}
            </div>

            <!-- Alerts -->
            <div style="background:#1A1D23;padding:20px;border-radius:8px;margin:16px 0">
                <h2 style="margin-top:0;color:{PRIMARY_COLOR}">
                    Warnings ({len(alerts)})
                </h2>
                {"<p style='color:#00C853'>Everything looks good — no warnings today.</p>" if not alerts else f"<table style='width:100%'>{alert_rows}</table>"}
            </div>

            <!-- Theme Monitor -->
            <div style="background:#1A1D23;padding:20px;border-radius:8px;margin:16px 0">
                <h2 style="margin-top:0">Your Investment Themes (Last Month)</h2>
                <table style="width:100%">{theme_html}</table>
            </div>

            <!-- Top Movers -->
            <div style="background:#1A1D23;padding:20px;border-radius:8px;margin:16px 0">
                <h2 style="margin-top:0">Biggest Winners &amp; Losers Today</h2>
                <table style="width:100%">
                    <tr style="color:#999"><td>Name</td><td style="text-align:right">Change</td><td style="text-align:right">EUR</td></tr>
                    {movers_html}
                </table>
            </div>

            {"<div style='background:#1A1D23;padding:20px;border-radius:8px;margin:16px 0'><h2 style='margin-top:0'>Worth a Look (Big Drops)</h2><p style='color:#999;font-size:13px'>These positions have fallen a lot from what you paid — could be a buying opportunity.</p><table style='width:100%'>" + opportunities_html + "</table></div>" if opportunities_html else ""}

            {"<div style='background:#1A1D23;padding:20px;border-radius:8px;margin:16px 0'><h2 style='margin-top:0'>Fund Rating Changes</h2><table style='width:100%'>" + mstar_html + "</table></div>" if mstar_html else ""}

            <p style="color:#666;font-size:12px;text-align:center;margin-top:40px">
                InvestmentMonitor &mdash; Your daily investment update
            </p>
        </div>
    </body>
    </html>
    """
    return html


def main():
    init_db()
    seed_default_alerts()  # Idempotent — only seeds if no rules exist

    positions = get_positions()
    if positions.empty:
        print(json.dumps({"has_alerts": False, "briefing": False, "reason": "no_positions"}))
        return

    tickers = list(set(positions["ticker"].tolist()))

    # Fetch all data
    prices = fetch_prices_no_cache(tickers)
    hist = fetch_history_no_cache(tickers, period="3mo")
    vix = fetch_vix_no_cache()
    fx_rates = fetch_fx_rates_no_cache()
    theme_perf = fetch_theme_performance_no_cache(period="1mo")
    fx_changes = fetch_fx_daily_changes_no_cache()
    morningstar_data = fetch_morningstar_ratings_no_cache()
    indices = fetch_benchmark_indices_no_cache()

    # Compute regime
    current_vix = None
    if not vix.empty:
        current_vix = vix["Close"].iloc[-1]

    yield_spread = fetch_yield_spread_no_cache()

    # Sector momentum for regime
    sector_tickers = {"XLK", "XLV", "XLF", "XLY", "XLI", "XLE", "XLU", "XLRE", "XLB", "XLC", "XLP"}
    sector_positive = None
    try:
        sector_hist = yf.download(list(sector_tickers), period="1mo", progress=False)
        if not sector_hist.empty:
            pos_count = 0
            for st_ticker in sector_tickers:
                if st_ticker in sector_hist.columns.get_level_values(0):
                    closes = sector_hist[st_ticker]["Close"].dropna()
                    if len(closes) >= 2 and closes.iloc[-1] > closes.iloc[0]:
                        pos_count += 1
            sector_positive = pos_count / len(sector_tickers)
    except Exception:
        pass

    regime_score = market_regime_score(
        vix=current_vix,
        yield_spread=yield_spread,
        momentum_pct_positive=sector_positive,
    )

    # Save regime history
    save_regime_score(
        dt=date.today().isoformat(),
        score=regime_score,
        vix=current_vix,
        yield_spread=yield_spread,
        momentum_pct=sector_positive,
    )

    regime_data = {"score": regime_score}

    # Run alert evaluation with all new data
    alerts = run_alert_evaluation(
        prices, hist, vix,
        regime_data=regime_data,
        theme_perf=theme_perf,
        fx_changes=fx_changes,
        morningstar_data=morningstar_data,
        fx_rates=fx_rates,
    )

    # AI Advisor note (graceful — never blocks the email)
    advisor_html = ""
    try:
        from data.advisor_engine import generate_daily_analysis
        advisor_result = generate_daily_analysis()
        if advisor_result.get("text"):
            # Convert markdown-like text to simple HTML
            advisor_text = advisor_result["text"]
            # Wrap paragraphs in <p> tags, preserve line breaks
            paragraphs = advisor_text.split("\n\n")
            formatted = "".join(
                f"<p style='margin:8px 0'>{p.replace(chr(10), '<br>')}</p>"
                for p in paragraphs if p.strip()
            )
            advisor_html = f"""
            <div style="background:#1A1D23;padding:20px;border-radius:8px;margin:16px 0;border-left:4px solid {PRIMARY_COLOR}">
                <h2 style="margin-top:0;color:{PRIMARY_COLOR}">AI Advisor's Note</h2>
                {formatted}
                <p style="color:#666;font-size:11px;margin-top:12px">
                    Generated by AI ({advisor_result.get('provider', 'N/A')}/{advisor_result.get('model', 'N/A')}).
                    This is informational analysis, not financial advice.
                </p>
            </div>"""
    except Exception as e:
        # Log but don't block email
        import logging
        logging.getLogger(__name__).warning("AI advisor note failed: %s", e)

    # Always build the full briefing email
    html = build_email_html(
        alerts, positions, prices,
        regime_score, current_vix, yield_spread,
        theme_perf, fx_changes, morningstar_data, fx_rates,
        indices,
    )

    # Inject AI advisor note before the closing footer
    if advisor_html:
        html = html.replace(
            '<p style="color:#666;font-size:12px;text-align:center;margin-top:40px">',
            advisor_html + '\n            <p style="color:#666;font-size:12px;text-align:center;margin-top:40px">',
        )

    # Build subject line (plain language)
    regime_label = "Pessimistic" if regime_score < 33 else ("Mixed Feelings" if regime_score < 66 else "Optimistic")
    alert_part = f"{len(alerts)} warning(s)" if alerts else "All clear"
    subject = f"InvestmentMonitor: {alert_part} | Mood: {regime_label} ({regime_score:.0f}) | {date.today().isoformat()}"

    output = {
        "has_alerts": len(alerts) > 0,
        "alert_count": len(alerts),
        "briefing": True,
        "email_to": ALERT_EMAIL,
        "email_subject": subject,
        "email_html": html,
        "alerts": alerts,
        "regime_score": regime_score,
        "regime_label": regime_label,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
