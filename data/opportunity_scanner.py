"""Automated opportunity scanner for the portfolio.

Scans for sector momentum, drawdown opportunities, theme divergence,
and correlation-based diversification opportunities using existing
yfinance data. No new data sources required.
"""

import logging
from datetime import date

import yfinance as yf

from config.settings import THEME_ETFS, THEME_TICKER_GROUPS
from data.database import (
    get_morningstar_cache,
    get_positions,
    save_opportunity,
)

logger = logging.getLogger(__name__)


def scan_sector_opportunities() -> list[dict]:
    """Compare theme ETF momentum against portfolio weights.

    Flags rising sectors where portfolio has zero or low exposure.
    """
    positions = get_positions()
    if positions.empty:
        return []

    # Get total portfolio value (approximate via cost basis)
    total_cost = positions["cost_basis"].sum()

    # Theme weights in portfolio
    theme_weights = {}
    for theme, tickers in THEME_TICKER_GROUPS.items():
        theme_cost = positions[positions["ticker"].isin(tickers)]["cost_basis"].sum()
        theme_weights[theme] = (theme_cost / total_cost * 100) if total_cost > 0 else 0

    # Theme ETF momentum
    opportunities = []
    for theme, etf in THEME_ETFS.items():
        if theme == "KOSPI":
            continue  # Index, not investable ETF
        try:
            t = yf.Ticker(etf)
            hist = t.history(period="1mo")
            if len(hist) < 2:
                continue
            ret_1m = ((hist["Close"].iloc[-1] / hist["Close"].iloc[0]) - 1) * 100

            # Find matching portfolio theme
            portfolio_weight = 0
            for p_theme, weight in theme_weights.items():
                if theme.lower() in p_theme.lower() or p_theme.lower() in theme.lower():
                    portfolio_weight = weight
                    break

            # Rising sector with low/zero portfolio exposure
            if ret_1m > 5 and portfolio_weight < 5:
                signal = min(ret_1m / 5, 3.0)  # Cap at 3.0
                opp = {
                    "scan_type": "sector_momentum",
                    "ticker_or_theme": f"{theme} ({etf})",
                    "signal_strength": round(signal, 2),
                    "detail": f"{theme} ETF ({etf}) up {ret_1m:+.1f}% in 1M, "
                              f"portfolio weight only {portfolio_weight:.1f}%",
                }
                opportunities.append(opp)
                save_opportunity(**opp)

        except Exception as e:
            logger.warning("Failed to scan %s: %s", etf, e)

    return opportunities


def scan_drawdown_opportunities() -> list[dict]:
    """Find positions with deep drawdowns but good Morningstar ratings."""
    positions = get_positions()
    if positions.empty:
        return []

    morningstar = get_morningstar_cache()
    ms_ratings = {}
    if not morningstar.empty:
        for _, r in morningstar.iterrows():
            ms_ratings[r["isin"]] = r.get("star_rating")

    opportunities = []
    for _, pos in positions.iterrows():
        ticker = pos["ticker"]
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="3mo")
            if hist.empty:
                continue

            current = hist["Close"].iloc[-1]
            peak = hist["Close"].max()
            drawdown = ((current - peak) / peak * 100) if peak > 0 else 0

            if drawdown < -10:
                # Check Morningstar rating (if available)
                star = ms_ratings.get(ticker)
                has_good_rating = star is not None and star >= 3

                signal = abs(drawdown) / 10  # Deeper drawdown = stronger signal
                if has_good_rating:
                    signal *= 1.5  # Boost if fundamentally sound

                opp = {
                    "scan_type": "drawdown_opportunity",
                    "ticker_or_theme": f"{pos['name']} ({ticker})",
                    "signal_strength": round(min(signal, 3.0), 2),
                    "detail": f"{pos['name']} down {drawdown:.1f}% from 3M peak"
                              + (f", Morningstar {star} stars" if star else ""),
                }
                opportunities.append(opp)
                save_opportunity(**opp)

        except Exception as e:
            logger.warning("Failed drawdown scan for %s: %s", ticker, e)

    return opportunities


def scan_theme_divergence() -> list[dict]:
    """Flag themes where ETF benchmark outperforms but portfolio holdings lag."""
    positions = get_positions()
    if positions.empty:
        return []

    opportunities = []
    theme_to_etf = {
        "Korea": "EWY",
        "Commodities/Mining": "GDX",
        "Nuclear/Uranium": "URA",
        "Semiconductors": "SMH",
    }

    for theme, etf in theme_to_etf.items():
        theme_tickers = THEME_TICKER_GROUPS.get(theme, [])
        if not theme_tickers:
            continue

        try:
            # ETF benchmark performance
            etf_hist = yf.Ticker(etf).history(period="1mo")
            if len(etf_hist) < 2:
                continue
            etf_ret = ((etf_hist["Close"].iloc[-1] / etf_hist["Close"].iloc[0]) - 1) * 100

            # Portfolio holdings average performance
            holding_rets = []
            for ticker in theme_tickers:
                if ticker not in positions["ticker"].values:
                    continue
                try:
                    h = yf.Ticker(ticker).history(period="1mo")
                    if len(h) >= 2:
                        ret = ((h["Close"].iloc[-1] / h["Close"].iloc[0]) - 1) * 100
                        holding_rets.append(ret)
                except Exception:
                    continue

            if not holding_rets:
                continue

            avg_holding_ret = sum(holding_rets) / len(holding_rets)
            divergence = etf_ret - avg_holding_ret

            # ETF up, holdings down or lagging significantly
            if etf_ret > 2 and divergence > 5:
                signal = min(divergence / 5, 3.0)
                opp = {
                    "scan_type": "theme_divergence",
                    "ticker_or_theme": theme,
                    "signal_strength": round(signal, 2),
                    "detail": f"{theme}: ETF ({etf}) {etf_ret:+.1f}% vs "
                              f"holdings avg {avg_holding_ret:+.1f}% (gap: {divergence:.1f}pp)",
                }
                opportunities.append(opp)
                save_opportunity(**opp)

        except Exception as e:
            logger.warning("Failed divergence scan for %s: %s", theme, e)

    return opportunities


def run_all_scans() -> list[dict]:
    """Run all opportunity scans and return combined results."""
    all_opportunities = []
    all_opportunities.extend(scan_sector_opportunities())
    all_opportunities.extend(scan_drawdown_opportunities())
    all_opportunities.extend(scan_theme_divergence())

    # Sort by signal strength descending
    all_opportunities.sort(key=lambda x: x.get("signal_strength", 0), reverse=True)
    return all_opportunities
