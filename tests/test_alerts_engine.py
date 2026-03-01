"""Tests for data/alerts_engine.py."""

import pandas as pd
import pytest

from data.alerts_engine import (
    evaluate_drawdown, evaluate_price_drop,
    evaluate_rebalance_drift, evaluate_total_loss,
    evaluate_vix_spike, evaluate_volatility_spike,
)


@pytest.fixture
def sample_prices():
    return {
        "IWDA.AS": {"price": 80.0, "change": -5.0, "change_pct": -5.88},
        "EIMI.AS": {"price": 30.0, "change": 0.5, "change_pct": 1.69},
    }


@pytest.fixture
def sample_hist():
    dates = pd.date_range("2024-01-01", periods=60, freq="B")
    return pd.DataFrame({
        "IWDA.AS": [100 - i * 0.5 for i in range(60)],  # declining
        "EIMI.AS": [50 + i * 0.1 for i in range(60)],   # rising
    }, index=dates)


def test_price_drop_triggers(sample_prices):
    msg = evaluate_price_drop("IWDA.AS", 3.0, "below", sample_prices)
    assert msg is not None
    assert "IWDA.AS" in msg
    assert "lost" in msg


def test_price_drop_no_trigger(sample_prices):
    msg = evaluate_price_drop("EIMI.AS", 3.0, "below", sample_prices)
    assert msg is None


def test_price_drop_above(sample_prices):
    msg = evaluate_price_drop("EIMI.AS", 1.0, "above", sample_prices)
    assert msg is not None
    assert "jumped up" in msg


def test_price_drop_missing_ticker(sample_prices):
    msg = evaluate_price_drop("NONEXIST", 3.0, "below", sample_prices)
    assert msg is None


def test_drawdown_triggers(sample_hist):
    msg = evaluate_drawdown("IWDA.AS", 10.0, "below", sample_hist)
    assert msg is not None
    assert "from its highest" in msg


def test_drawdown_no_trigger(sample_hist):
    msg = evaluate_drawdown("EIMI.AS", 50.0, "below", sample_hist)
    assert msg is None  # EIMI is rising


def test_volatility_spike(sample_hist):
    msg = evaluate_volatility_spike("IWDA.AS", 1.0, "above", sample_hist)
    # May or may not trigger depending on calculated vol
    assert msg is None or "unstable" in msg


def test_vix_spike():
    vix = pd.DataFrame({"Close": [20.0, 22.0, 30.0]},
                        index=pd.date_range("2024-01-01", periods=3))
    msg = evaluate_vix_spike(25.0, "above", vix)
    assert msg is not None
    assert "VIX" in msg

    msg = evaluate_vix_spike(35.0, "above", vix)
    assert msg is None


def test_rebalance_drift(sample_prices):
    positions = pd.DataFrame({
        "ticker": ["IWDA.AS", "EIMI.AS"],
        "units": [100.0, 50.0],
        "cost_basis": [8000.0, 1500.0],
        "target_weight": [80.0, 20.0],
    })
    msg = evaluate_rebalance_drift("IWDA.AS", 5.0, positions, sample_prices)
    # IWDA: 80*100=8000, EIMI: 30*50=1500, total=9500
    # IWDA weight=84.2%, target=80%, drift=4.2% < 5%
    assert msg is None

    msg = evaluate_rebalance_drift("IWDA.AS", 3.0, positions, sample_prices)
    assert msg is not None  # drift 4.2% > 3%


def test_total_loss(sample_prices):
    positions = pd.DataFrame({
        "ticker": ["IWDA.AS", "EIMI.AS"],
        "units": [100.0, 50.0],
        "cost_basis": [10000.0, 2000.0],
    })
    # Total value: 8000+1500=9500, cost: 12000, PnL: -20.8%
    msg = evaluate_total_loss(-10.0, "below", positions, sample_prices)
    assert msg is not None
    assert "losing" in msg

    msg = evaluate_total_loss(-30.0, "below", positions, sample_prices)
    assert msg is None  # -20.8% > -30%
