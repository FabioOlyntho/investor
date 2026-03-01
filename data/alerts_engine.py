"""Alert rule evaluation engine."""

from datetime import date
from typing import Optional

import pandas as pd

from config.settings import ALERT_TYPES, VIX_TICKER
from data.database import (
    add_alert_history, alert_fired_today, get_alert_configs,
    get_positions,
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
        return f"{ticker} dropped {change_pct:.2f}% today (threshold: -{abs(threshold):.1f}%)"
    if direction == "above" and change_pct > threshold:
        return f"{ticker} gained {change_pct:.2f}% today (threshold: +{threshold:.1f}%)"
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
        return f"{ticker} drawdown at {current_dd:.1f}% from peak (threshold: -{abs(threshold):.1f}%)"
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
        return f"{ticker} volatility at {vol_30d:.1f}% (threshold: {threshold:.1f}%)"
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
        return f"VIX at {current:.1f} (threshold: {threshold:.1f})"
    if direction == "below" and current < threshold:
        return f"VIX at {current:.1f} (threshold: {threshold:.1f})"
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
            f"{ticker} weight {current_weight:.1f}% vs target {target:.1f}% "
            f"(drift: {drift:.1f}%, threshold: {threshold:.1f}%)"
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
        return f"Portfolio P&L at {pnl_pct:.1f}% (threshold: {threshold:.1f}%)"
    return None


def run_alert_evaluation(
    prices: dict[str, dict],
    hist: pd.DataFrame,
    vix_data: pd.DataFrame,
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
