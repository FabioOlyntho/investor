"""Tests for data/database.py."""

import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from data.database import (
    add_alert_config, add_alert_history, add_position, acknowledge_alert,
    alert_fired_today, delete_alert_config, delete_position,
    get_alert_configs, get_alert_history, get_morningstar_cache,
    get_morningstar_rating, get_positions, get_price_history,
    get_regime_history, init_db, save_morningstar_rating,
    save_price_history, save_regime_score, seed_default_alerts,
    update_position,
)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


def test_init_db(db_path):
    assert db_path.exists()


def test_add_and_get_position(db_path):
    pid = add_position(
        ticker="IWDA.AS", name="iShares World", units=100,
        cost_basis=8000.0, purchase_date="2024-01-15",
        sector="Equity - Global", asset_class="Equity",
        db_path=db_path,
    )
    assert pid > 0

    positions = get_positions(db_path)
    assert len(positions) == 1
    assert positions.iloc[0]["ticker"] == "IWDA.AS"
    assert positions.iloc[0]["units"] == 100


def test_update_position(db_path):
    pid = add_position(
        ticker="TEST", name="Test", units=10,
        cost_basis=100, purchase_date="2024-01-01",
        sector="Other", asset_class="Equity", db_path=db_path,
    )
    update_position(pid, db_path=db_path, units=20, name="Updated")
    positions = get_positions(db_path)
    assert positions.iloc[0]["units"] == 20
    assert positions.iloc[0]["name"] == "Updated"


def test_update_position_rejects_unknown_fields(db_path):
    pid = add_position(
        ticker="TEST", name="Test", units=10,
        cost_basis=100, purchase_date="2024-01-01",
        sector="Other", asset_class="Equity", db_path=db_path,
    )
    result = update_position(pid, db_path=db_path, bad_field="hack")
    assert result is False


def test_delete_position(db_path):
    pid = add_position(
        ticker="DEL", name="Delete Me", units=1,
        cost_basis=10, purchase_date="2024-01-01",
        sector="Other", asset_class="Equity", db_path=db_path,
    )
    assert delete_position(pid, db_path=db_path) is True
    assert len(get_positions(db_path)) == 0
    assert delete_position(999, db_path=db_path) is False


def test_price_history(db_path):
    df = pd.DataFrame({
        "Open": [100.0, 101.0],
        "High": [102.0, 103.0],
        "Low": [99.0, 100.0],
        "Close": [101.0, 102.0],
        "Volume": [1000, 1100],
    }, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))

    save_price_history("TEST", df, db_path)
    result = get_price_history("TEST", db_path=db_path)
    assert len(result) == 2
    assert result.iloc[0]["close"] == 101.0


def test_alert_config_crud(db_path):
    aid = add_alert_config(
        alert_type="price_drop", threshold=5.0,
        direction="below", severity="warning",
        ticker="IWDA.AS", db_path=db_path,
    )
    assert aid > 0

    configs = get_alert_configs(db_path)
    assert len(configs) == 1
    assert configs.iloc[0]["alert_type"] == "price_drop"

    delete_alert_config(aid, db_path)
    assert len(get_alert_configs(db_path)) == 0


def test_alert_history(db_path):
    ahid = add_alert_history(
        message="Test alert", severity="warning",
        db_path=db_path,
    )
    assert ahid > 0

    history = get_alert_history(db_path=db_path)
    assert len(history) == 1
    assert history.iloc[0]["acknowledged"] == 0

    acknowledge_alert(ahid, db_path)
    history = get_alert_history(db_path=db_path)
    assert history.iloc[0]["acknowledged"] == 1

    # Unacknowledged only
    unack = get_alert_history(unacknowledged_only=True, db_path=db_path)
    assert len(unack) == 0


# --- Regime History ---

def test_regime_history(db_path):
    save_regime_score("2024-01-01", 65.0, vix=18.0, yield_spread=0.5, momentum_pct=0.7, db_path=db_path)
    save_regime_score("2024-01-02", 70.0, vix=15.0, db_path=db_path)

    history = get_regime_history(limit=10, db_path=db_path)
    assert len(history) == 2
    assert history.iloc[0]["score"] == 70.0  # Most recent first
    assert history.iloc[1]["score"] == 65.0


def test_regime_upsert(db_path):
    save_regime_score("2024-01-01", 50.0, db_path=db_path)
    save_regime_score("2024-01-01", 60.0, db_path=db_path)  # Same date
    history = get_regime_history(limit=10, db_path=db_path)
    assert len(history) == 1
    assert history.iloc[0]["score"] == 60.0


# --- Morningstar Cache ---

def test_morningstar_cache(db_path):
    save_morningstar_rating(
        "ES0113693032", fund_name="Alken Small Cap",
        star_rating=5, previous_star_rating=5,
        medalist_rating="Silver", category="Europe Small-Cap",
        risk_rating="Above Average", db_path=db_path,
    )
    cache = get_morningstar_cache(db_path)
    assert len(cache) == 1
    assert cache.iloc[0]["star_rating"] == 5

    rating = get_morningstar_rating("ES0113693032", db_path)
    assert rating is not None
    assert rating["fund_name"] == "Alken Small Cap"

    # Non-existent
    assert get_morningstar_rating("FAKE123", db_path) is None


# --- Seed Default Alerts ---

def test_seed_default_alerts(db_path):
    # Initially empty
    assert len(get_alert_configs(db_path)) == 0

    seed_default_alerts(db_path)
    configs = get_alert_configs(db_path)
    assert len(configs) == 32

    # Idempotent — calling again should not add more
    seed_default_alerts(db_path)
    assert len(get_alert_configs(db_path)) == 32


def test_seed_has_all_alert_types(db_path):
    seed_default_alerts(db_path)
    configs = get_alert_configs(db_path)
    types = set(configs["alert_type"].tolist())
    expected = {
        "total_loss", "vix_spike", "correlation_spike",
        "market_regime_change", "price_drop", "drawdown",
        "sector_rotation", "concentration_risk", "currency_risk",
        "morningstar_downgrade",
    }
    assert expected == types
