"""Tests for the 6 new alert evaluators in data/alerts_engine.py."""

import numpy as np
import pandas as pd
import pytest

from data.alerts_engine import (
    evaluate_concentration_risk,
    evaluate_correlation_spike,
    evaluate_currency_risk,
    evaluate_market_regime_change,
    evaluate_morningstar_downgrade,
    evaluate_sector_rotation,
)
from data.database import init_db, save_regime_score


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test_alerts.db"
    init_db(path)
    return path


# --- market_regime_change ---

def test_regime_change_triggers(db_path):
    # Seed 5 days of history with score ~70
    for i in range(5):
        save_regime_score(f"2024-01-{10+i:02d}", 70.0, db_path=db_path)

    regime_data = {"score": 45.0}  # Dropped 25 pts
    msg = evaluate_market_regime_change(
        15.0, "below", regime_data, db_path=db_path
    )
    assert msg is not None
    assert "dropped" in msg
    assert "25" in msg or "25.0" in msg


def test_regime_change_no_trigger(db_path):
    for i in range(5):
        save_regime_score(f"2024-01-{10+i:02d}", 60.0, db_path=db_path)

    regime_data = {"score": 55.0}  # Dropped only 5 pts
    msg = evaluate_market_regime_change(
        15.0, "below", regime_data, db_path=db_path
    )
    assert msg is None


def test_regime_change_no_data():
    msg = evaluate_market_regime_change(15.0, "below", None)
    assert msg is None


# --- sector_rotation ---

def test_sector_rotation_triggers():
    theme_perf = {"EWY": -12.5, "URA": 5.0, "SMH": -3.0}
    msg = evaluate_sector_rotation("EWY", 10.0, "below", theme_perf)
    assert msg is not None
    assert "EWY" in msg
    assert "12.5" in msg


def test_sector_rotation_no_trigger():
    theme_perf = {"EWY": -5.0, "URA": 5.0}
    msg = evaluate_sector_rotation("EWY", 10.0, "below", theme_perf)
    assert msg is None


def test_sector_rotation_missing_ticker():
    theme_perf = {"URA": 5.0}
    msg = evaluate_sector_rotation("EWY", 10.0, "below", theme_perf)
    assert msg is None


# --- correlation_spike ---

def test_correlation_spike_triggers():
    # Create highly correlated data
    np.random.seed(42)
    base = np.cumsum(np.random.randn(40))
    dates = pd.date_range("2024-01-01", periods=40, freq="B")
    hist = pd.DataFrame({
        "A": base + np.random.randn(40) * 0.01,
        "B": base + np.random.randn(40) * 0.01,
        "C": base + np.random.randn(40) * 0.01,
    }, index=dates)
    msg = evaluate_correlation_spike(0.5, "above", hist)
    assert msg is not None
    assert "same direction" in msg


def test_correlation_spike_no_trigger():
    # Create uncorrelated data
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=40, freq="B")
    hist = pd.DataFrame({
        "A": np.cumsum(np.random.randn(40)),
        "B": np.cumsum(np.random.randn(40)),
        "C": np.cumsum(np.random.randn(40)),
    }, index=dates)
    msg = evaluate_correlation_spike(0.99, "above", hist)
    assert msg is None


def test_correlation_spike_insufficient_data():
    hist = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    msg = evaluate_correlation_spike(0.5, "above", hist)
    assert msg is None


# --- concentration_risk ---

def test_concentration_triggers():
    positions = pd.DataFrame({
        "ticker": ["IKRA.AS", "HKOR.L", "SMH.DE"],
        "units": [100.0, 200.0, 50.0],
        "cost_basis": [10000.0, 10000.0, 8000.0],
    })
    prices = {
        "IKRA.AS": {"price": 100.0, "currency": "EUR"},
        "HKOR.L": {"price": 50.0, "currency": "EUR"},
        "SMH.DE": {"price": 160.0, "currency": "EUR"},
    }
    # Korea: 10000 + 10000 = 20000, Total: 28000, weight = 71.4%
    msg = evaluate_concentration_risk(
        "Korea", 25.0, "above", positions, prices, {"EUR": 1.0}
    )
    assert msg is not None
    assert "Korea" in msg
    assert "Too much" in msg


def test_concentration_no_trigger():
    positions = pd.DataFrame({
        "ticker": ["IKRA.AS", "SMH.DE"],
        "units": [10.0, 100.0],
        "cost_basis": [1000.0, 16000.0],
    })
    prices = {
        "IKRA.AS": {"price": 100.0, "currency": "EUR"},
        "SMH.DE": {"price": 160.0, "currency": "EUR"},
    }
    # Korea: 1000, Total: 17000, weight = 5.9%
    msg = evaluate_concentration_risk(
        "Korea", 25.0, "above", positions, prices, {"EUR": 1.0}
    )
    assert msg is None


# --- currency_risk ---

def test_currency_risk_triggers():
    fx_changes = {
        "EUR/USD": {"rate": 1.0850, "change_pct": 2.5},
        "EUR/GBP": {"rate": 0.8600, "change_pct": 0.3},
    }
    msg = evaluate_currency_risk("EUR/USD", 2.0, "above", fx_changes)
    assert msg is not None
    assert "USD" in msg
    assert "2.5" in msg


def test_currency_risk_no_trigger():
    fx_changes = {
        "EUR/USD": {"rate": 1.0850, "change_pct": 0.5},
    }
    msg = evaluate_currency_risk("EUR/USD", 2.0, "above", fx_changes)
    assert msg is None


def test_currency_risk_missing_pair():
    msg = evaluate_currency_risk("EUR/JPY", 2.0, "above", {"EUR/USD": {"rate": 1.08, "change_pct": 0.1}})
    assert msg is None


# --- morningstar_downgrade ---

def test_morningstar_downgrade_triggers():
    mstar = [
        {"isin": "ES001", "fund_name": "Test Fund A", "star_rating": 3, "previous_star_rating": 5},
        {"isin": "ES002", "fund_name": "Test Fund B", "star_rating": 4, "previous_star_rating": 4},
    ]
    msg = evaluate_morningstar_downgrade(1.0, mstar)
    assert msg is not None
    assert "Test Fund A" in msg
    assert "5 stars" in msg


def test_morningstar_downgrade_critical_threshold():
    mstar = [
        {"isin": "ES001", "fund_name": "Minor Drop", "star_rating": 4, "previous_star_rating": 5},
    ]
    # Threshold 2 — drop of 1 is not enough
    msg = evaluate_morningstar_downgrade(2.0, mstar)
    assert msg is None


def test_morningstar_no_change():
    mstar = [
        {"isin": "ES001", "fund_name": "Stable Fund", "star_rating": 4, "previous_star_rating": 4},
    ]
    msg = evaluate_morningstar_downgrade(1.0, mstar)
    assert msg is None


def test_morningstar_no_data():
    msg = evaluate_morningstar_downgrade(1.0, None)
    assert msg is None
    msg = evaluate_morningstar_downgrade(1.0, [])
    assert msg is None
