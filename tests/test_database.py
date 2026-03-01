"""Tests for data/database.py."""

import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from data.database import (
    add_alert_config, add_alert_history, add_position, acknowledge_alert,
    alert_fired_today, delete_alert_config, delete_position,
    get_alert_configs, get_alert_history, get_positions,
    get_price_history, init_db, save_price_history,
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
