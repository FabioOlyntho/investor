"""CLI script for n8n cron — daily alert evaluation + email output.

Usage:
    python -m cli.daily_update

Exits with code 0 and prints HTML email body to stdout if alerts triggered.
Exits with code 0 and prints nothing if no alerts.
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import yfinance as yf

from config.settings import ALERT_EMAIL, PRIMARY_COLOR, SEVERITY_COLORS
from data.database import get_positions, init_db
from data.alerts_engine import run_alert_evaluation


def fetch_prices_no_cache(tickers: list[str]) -> dict[str, dict]:
    """Fetch prices without Streamlit cache (for CLI use)."""
    result = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            if hist.empty:
                continue
            current = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) >= 2 else current
            change = current - prev
            change_pct = (change / prev * 100) if prev != 0 else 0.0
            result[ticker] = {
                "price": current,
                "change": change,
                "change_pct": change_pct,
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


def build_email_html(
    alerts: list[dict],
    positions: pd.DataFrame,
    prices: dict[str, dict],
) -> str:
    """Build HTML email body with portfolio summary + alerts."""
    today = date.today().strftime("%d %B %Y")

    # Portfolio summary
    total_value = 0
    total_cost = 0
    for _, pos in positions.iterrows():
        t = pos["ticker"]
        if t in prices:
            total_value += pos["units"] * prices[t]["price"]
        total_cost += pos["cost_basis"]
    pnl = total_value - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0

    alert_rows = ""
    for a in alerts:
        color = SEVERITY_COLORS.get(a["severity"], "#78909C")
        alert_rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #333">
                <span style="color:{color};font-weight:bold">{a['severity'].upper()}</span>
            </td>
            <td style="padding:8px;border-bottom:1px solid #333">{a['message']}</td>
        </tr>"""

    pnl_color = "#00C853" if pnl >= 0 else "#FF1744"

    html = f"""
    <html>
    <body style="background:#0E1117;color:#FAFAFA;font-family:Arial,sans-serif;padding:20px">
        <div style="max-width:600px;margin:0 auto">
            <h1 style="color:{PRIMARY_COLOR}">InvestmentMonitor Daily Report</h1>
            <p style="color:#999">{today}</p>

            <div style="background:#1A1D23;padding:20px;border-radius:8px;margin:20px 0">
                <h2 style="margin-top:0">Portfolio Summary</h2>
                <table style="width:100%">
                    <tr>
                        <td>Total Value</td>
                        <td style="text-align:right;font-weight:bold">&euro;{total_value:,.2f}</td>
                    </tr>
                    <tr>
                        <td>Total P&amp;L</td>
                        <td style="text-align:right;color:{pnl_color};font-weight:bold">
                            &euro;{pnl:+,.2f} ({pnl_pct:+.1f}%)
                        </td>
                    </tr>
                    <tr>
                        <td>Positions</td>
                        <td style="text-align:right">{len(positions)}</td>
                    </tr>
                </table>
            </div>

            <div style="background:#1A1D23;padding:20px;border-radius:8px;margin:20px 0">
                <h2 style="margin-top:0;color:{PRIMARY_COLOR}">
                    Alerts ({len(alerts)})
                </h2>
                <table style="width:100%">
                    {alert_rows}
                </table>
            </div>

            <p style="color:#666;font-size:12px;text-align:center;margin-top:40px">
                InvestmentMonitor &mdash; Automated alert from n8n cron
            </p>
        </div>
    </body>
    </html>
    """
    return html


def main():
    init_db()
    positions = get_positions()

    if positions.empty:
        return

    tickers = positions["ticker"].tolist()
    prices = fetch_prices_no_cache(tickers)
    hist = fetch_history_no_cache(tickers, period="3mo")
    vix = fetch_vix_no_cache()

    alerts = run_alert_evaluation(prices, hist, vix)

    if alerts:
        html = build_email_html(alerts, positions, prices)
        # Output JSON for n8n to parse
        output = {
            "has_alerts": True,
            "alert_count": len(alerts),
            "email_to": ALERT_EMAIL,
            "email_subject": f"InvestmentMonitor: {len(alerts)} alert(s) - {date.today().isoformat()}",
            "email_html": html,
            "alerts": alerts,
        }
        print(json.dumps(output))
    else:
        print(json.dumps({"has_alerts": False}))


if __name__ == "__main__":
    main()
