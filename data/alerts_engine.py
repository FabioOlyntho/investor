"""Alert rule evaluation engine."""

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from config.settings import ALERT_TYPES, THEME_TICKER_GROUPS, VIX_TICKER
from data.database import (
    add_alert_history, alert_fired_today, get_alert_configs,
    get_positions, get_regime_history,
)


def evaluate_price_drop(
    ticker: str, threshold: float, direction: str,
    prices: dict[str, dict],
) -> Optional[str]:
    """Check if daily change exceeds threshold."""
    if ticker not in prices:
        return None
    change_pct = prices[ticker]["change_pct"]
    if direction == "below" and change_pct < -abs(threshold):
        return f"{ticker} lost {abs(change_pct):.2f}% today (your limit was {abs(threshold):.1f}%)"
    if direction == "above" and change_pct > threshold:
        return f"{ticker} jumped up {change_pct:.2f}% today (your limit was {threshold:.1f}%)"
    return None


def evaluate_drawdown(
    ticker: str, threshold: float, direction: str,
    hist: pd.DataFrame,
) -> Optional[str]:
    """Check if drawdown from peak exceeds threshold."""
    if ticker not in hist.columns:
        return None
    prices = hist[ticker].dropna()
    if len(prices) < 2:
        return None
    peak = prices.cummax()
    current_dd = ((prices.iloc[-1] - peak.iloc[-1]) / peak.iloc[-1]) * 100
    if direction == "below" and current_dd < -abs(threshold):
        return f"{ticker} is down {abs(current_dd):.1f}% from its highest point (your limit was {abs(threshold):.1f}%)"
    return None


def evaluate_volatility_spike(
    ticker: str, threshold: float, direction: str,
    hist: pd.DataFrame,
) -> Optional[str]:
    """Check if 30-day annualized volatility exceeds threshold."""
    if ticker not in hist.columns:
        return None
    returns = hist[ticker].pct_change().dropna()
    if len(returns) < 30:
        return None
    vol_30d = returns.tail(30).std() * (252 ** 0.5) * 100
    if direction == "above" and vol_30d > threshold:
        return f"{ticker} is very unstable right now — swinging {vol_30d:.1f}% per year (your limit was {threshold:.1f}%)"
    return None


def evaluate_vix_spike(
    threshold: float, direction: str,
    vix_data: pd.DataFrame,
) -> Optional[str]:
    """Check if VIX exceeds threshold."""
    if vix_data.empty:
        return None
    current = vix_data["Close"].iloc[-1]
    if direction == "above" and current > threshold:
        return f"Fear Index (VIX) is at {current:.1f} — markets are nervous (your limit was {threshold:.1f})"
    if direction == "below" and current < threshold:
        return f"Fear Index (VIX) dropped to {current:.1f} — markets are calming down (your limit was {threshold:.1f})"
    return None


def evaluate_rebalance_drift(
    ticker: str, threshold: float,
    positions: pd.DataFrame, prices: dict[str, dict],
) -> Optional[str]:
    """Check if position weight drifts from target."""
    pos = positions[positions["ticker"] == ticker]
    if pos.empty:
        return None
    pos = pos.iloc[0]
    target = pos.get("target_weight")
    if target is None or pd.isna(target) or target == 0:
        return None
    if ticker not in prices:
        return None

    # Calculate current weight
    total_value = 0
    for _, p in positions.iterrows():
        t = p["ticker"]
        if t in prices:
            total_value += p["units"] * prices[t]["price"]
    if total_value == 0:
        return None

    current_value = pos["units"] * prices[ticker]["price"]
    current_weight = (current_value / total_value) * 100
    drift = abs(current_weight - target)

    if drift > threshold:
        return (
            f"{ticker} is now {current_weight:.1f}% of your portfolio "
            f"but your target was {target:.1f}% — off by {drift:.1f}%"
        )
    return None


def evaluate_total_loss(
    threshold: float, direction: str,
    positions: pd.DataFrame, prices: dict[str, dict],
) -> Optional[str]:
    """Check if total portfolio P&L drops below threshold."""
    total_value = 0
    total_cost = 0
    for _, pos in positions.iterrows():
        t = pos["ticker"]
        if t in prices:
            total_value += pos["units"] * prices[t]["price"]
        total_cost += pos["cost_basis"]

    if total_cost == 0:
        return None
    pnl_pct = ((total_value - total_cost) / total_cost) * 100

    if direction == "below" and pnl_pct < threshold:
        return f"Your portfolio is losing {abs(pnl_pct):.1f}% overall (your limit was {abs(threshold):.1f}%)"
    return None


def evaluate_market_regime_change(
    threshold: float, direction: str,
    regime_data: dict = None,
    db_path=None,
) -> Optional[str]:
    """Check if regime score dropped significantly vs 5-day average."""
    if regime_data is None:
        return None
    current_score = regime_data.get("score")
    if current_score is None:
        return None

    history = get_regime_history(limit=5, db_path=db_path)
    if history.empty or len(history) < 2:
        return None

    avg_score = history["score"].mean()
    delta = current_score - avg_score

    if direction == "below" and delta < -abs(threshold):
        return (
            f"Market mood changed fast — confidence dropped {abs(delta):.0f} points "
            f"(now {current_score:.0f}/100, was averaging {avg_score:.0f} last 5 days)"
        )
    return None


def evaluate_sector_rotation(
    ticker: str, threshold: float, direction: str,
    theme_perf: dict[str, float] = None,
) -> Optional[str]:
    """Check if theme ETF 1-month return signals momentum reversal."""
    if theme_perf is None or ticker not in theme_perf:
        return None
    ret = theme_perf[ticker]
    if direction == "below" and ret < -abs(threshold):
        return (
            f"The {ticker} sector fund lost {abs(ret):.1f}% this month "
            f"— this area of the market is falling"
        )
    return None


def evaluate_correlation_spike(
    threshold: float, direction: str,
    hist: pd.DataFrame,
) -> Optional[str]:
    """Check if mean pairwise portfolio correlation exceeds threshold."""
    if hist.empty or len(hist.columns) < 2:
        return None
    returns = hist.pct_change().dropna()
    if len(returns) < 20:
        return None
    corr = returns.tail(30).corr()
    # Mean of upper triangle (excluding diagonal)
    mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)
    mean_corr = corr.values[mask].mean()
    if np.isnan(mean_corr):
        return None
    if direction == "above" and mean_corr > threshold:
        return (
            f"Your investments are all moving in the same direction ({mean_corr:.0%} similar) "
            f"— less diversification protection right now"
        )
    return None


def evaluate_concentration_risk(
    theme: str, threshold: float, direction: str,
    positions: pd.DataFrame, prices: dict[str, dict],
    fx_rates: dict[str, float] = None,
) -> Optional[str]:
    """Check if a theme's weight exceeds threshold."""
    theme_tickers = THEME_TICKER_GROUPS.get(theme, [])
    if not theme_tickers:
        return None

    from data.market_data import convert_to_eur

    total_value = 0
    theme_value = 0
    for _, pos in positions.iterrows():
        t = pos["ticker"]
        if t not in prices:
            continue
        p = prices[t]
        currency = p.get("currency", "EUR")
        rate = fx_rates or {}
        price_eur = convert_to_eur(p["price"], currency, rate)
        mv = pos["units"] * price_eur
        total_value += mv
        if t in theme_tickers:
            theme_value += mv

    if total_value == 0:
        return None
    weight = (theme_value / total_value) * 100

    if direction == "above" and weight > threshold:
        return (
            f"Too much money in {theme} — it's {weight:.1f}% of your portfolio "
            f"(your max was {threshold:.0f}%)"
        )
    return None


def evaluate_currency_risk(
    pair: str, threshold: float, direction: str,
    fx_changes: dict[str, dict] = None,
) -> Optional[str]:
    """Check if daily FX move exceeds threshold."""
    if fx_changes is None or pair not in fx_changes:
        return None
    change_pct = fx_changes[pair].get("change_pct", 0)
    if direction == "above" and abs(change_pct) > threshold:
        rate = fx_changes[pair].get("rate", 0)
        direction_word = "stronger" if change_pct > 0 else "weaker"
        return (
            f"The euro got {direction_word} against {pair.split('/')[1]} today ({change_pct:+.2f}%) "
            f"— this affects the value of your non-euro investments"
        )
    return None


def evaluate_morningstar_downgrade(
    threshold: float,
    morningstar_data: list[dict] = None,
) -> Optional[str]:
    """Check if any fund's star rating dropped by >= threshold stars."""
    if not morningstar_data:
        return None
    messages = []
    for fund in morningstar_data:
        current = fund.get("star_rating")
        previous = fund.get("previous_star_rating")
        if current is None or previous is None:
            continue
        drop = previous - current
        if drop >= threshold:
            name = fund.get("fund_name", fund.get("isin", "Unknown"))
            messages.append(
                f"{name} was downgraded by Morningstar: {previous} stars → {current} stars "
                f"(lost {drop} star{'s' if drop > 1 else ''})"
            )
    if messages:
        return "; ".join(messages)
    return None


def run_alert_evaluation(
    prices: dict[str, dict],
    hist: pd.DataFrame,
    vix_data: pd.DataFrame,
    *,
    regime_data: dict = None,
    theme_perf: dict[str, float] = None,
    fx_changes: dict[str, dict] = None,
    morningstar_data: list[dict] = None,
    fx_rates: dict[str, float] = None,
    db_path=None,
) -> list[dict]:
    """Evaluate all enabled alert rules and return triggered alerts."""
    configs = get_alert_configs(db_path)
    positions = get_positions(db_path)
    triggered = []

    for _, cfg in configs.iterrows():
        if not cfg["enabled"]:
            continue

        alert_type = cfg["alert_type"]
        ticker = cfg["ticker"]
        threshold = cfg["threshold"]
        direction = cfg["direction"]
        severity = cfg["severity"]
        config_id = int(cfg["id"])

        # Dedup: skip if already fired today
        if alert_fired_today(alert_type, ticker, db_path):
            continue

        message = None

        if alert_type == "price_drop" and ticker:
            message = evaluate_price_drop(ticker, threshold, direction, prices)
        elif alert_type == "drawdown" and ticker:
            message = evaluate_drawdown(ticker, threshold, direction, hist)
        elif alert_type == "volatility_spike" and ticker:
            message = evaluate_volatility_spike(ticker, threshold, direction, hist)
        elif alert_type == "vix_spike":
            message = evaluate_vix_spike(threshold, direction, vix_data)
        elif alert_type == "rebalance_drift" and ticker:
            message = evaluate_rebalance_drift(ticker, threshold, positions, prices)
        elif alert_type == "total_loss":
            message = evaluate_total_loss(threshold, direction, positions, prices)
        elif alert_type == "market_regime_change":
            message = evaluate_market_regime_change(
                threshold, direction, regime_data, db_path)
        elif alert_type == "sector_rotation" and ticker:
            message = evaluate_sector_rotation(
                ticker, threshold, direction, theme_perf)
        elif alert_type == "correlation_spike":
            message = evaluate_correlation_spike(threshold, direction, hist)
        elif alert_type == "concentration_risk" and ticker:
            message = evaluate_concentration_risk(
                ticker, threshold, direction, positions, prices, fx_rates)
        elif alert_type == "currency_risk" and ticker:
            message = evaluate_currency_risk(
                ticker, threshold, direction, fx_changes)
        elif alert_type == "morningstar_downgrade":
            message = evaluate_morningstar_downgrade(
                threshold, morningstar_data)

        if message:
            alert_id = add_alert_history(
                message=message, severity=severity,
                config_id=config_id, db_path=db_path,
            )
            triggered.append({
                "id": alert_id,
                "message": message,
                "severity": severity,
                "alert_type": alert_type,
                "ticker": ticker,
            })

    return triggered
