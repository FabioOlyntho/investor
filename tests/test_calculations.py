"""Tests for data/calculations.py."""

import numpy as np
import pandas as pd
import pytest

from data.calculations import (
    annualized_return, annualized_volatility, beta, correlation_matrix,
    cumulative_returns, daily_returns, drawdown_series, market_regime_score,
    max_drawdown, rolling_returns, rolling_volatility, sharpe_ratio,
    value_at_risk,
)


@pytest.fixture
def sample_prices():
    """100-day price series with upward trend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.01, 100)
    prices = 100 * np.cumprod(1 + returns)
    return pd.Series(prices, index=dates)


@pytest.fixture
def sample_returns(sample_prices):
    return daily_returns(sample_prices)


def test_daily_returns(sample_prices):
    rets = daily_returns(sample_prices)
    assert len(rets) == len(sample_prices) - 1
    assert not rets.isna().any()


def test_cumulative_returns(sample_returns):
    cum = cumulative_returns(sample_returns)
    assert len(cum) == len(sample_returns)
    assert cum.iloc[0] == pytest.approx(sample_returns.iloc[0], rel=1e-6)


def test_annualized_return(sample_returns):
    ann = annualized_return(sample_returns)
    assert isinstance(ann, float)
    assert -1.0 < ann < 5.0  # reasonable range


def test_annualized_volatility(sample_returns):
    vol = annualized_volatility(sample_returns)
    assert vol > 0
    assert vol < 1.0  # less than 100%


def test_sharpe_ratio(sample_returns):
    sr = sharpe_ratio(sample_returns)
    assert isinstance(sr, float)
    assert -10 < sr < 10


def test_sharpe_zero_vol():
    flat = pd.Series([0.0] * 50)
    assert sharpe_ratio(flat) == 0.0


def test_max_drawdown(sample_prices):
    dd = max_drawdown(sample_prices)
    assert dd <= 0.0
    assert dd >= -1.0


def test_drawdown_series(sample_prices):
    dd = drawdown_series(sample_prices)
    assert len(dd) == len(sample_prices)
    assert (dd <= 0).all()


def test_value_at_risk(sample_returns):
    var = value_at_risk(sample_returns, confidence=0.95)
    assert var < 0  # VaR is negative


def test_beta():
    np.random.seed(42)
    benchmark = pd.Series(np.random.normal(0.001, 0.01, 100))
    # Correlated portfolio
    portfolio = benchmark * 1.2 + pd.Series(np.random.normal(0, 0.002, 100))
    b = beta(portfolio, benchmark)
    assert 0.5 < b < 2.0  # should be close to 1.2


def test_correlation_matrix():
    np.random.seed(42)
    data = pd.DataFrame({
        "A": np.random.normal(0, 1, 100),
        "B": np.random.normal(0, 1, 100),
    })
    corr = correlation_matrix(data)
    assert corr.shape == (2, 2)
    assert corr.loc["A", "A"] == pytest.approx(1.0, abs=0.01)


def test_rolling_volatility(sample_returns):
    rv = rolling_volatility(sample_returns, window=20)
    assert len(rv) == len(sample_returns)
    valid = rv.dropna()
    assert len(valid) > 0
    assert (valid > 0).all()


def test_rolling_returns(sample_returns):
    rr = rolling_returns(sample_returns, window=20)
    assert len(rr) == len(sample_returns)


def test_market_regime_score():
    # Full risk-on
    score = market_regime_score(vix=10, yield_spread=1.0, momentum_pct_positive=1.0)
    assert score == 100.0

    # Full risk-off
    score = market_regime_score(vix=40, yield_spread=-1.0, momentum_pct_positive=0.0)
    assert score == 0.0

    # Mixed
    score = market_regime_score(vix=20, yield_spread=0.25, momentum_pct_positive=0.5)
    assert 20 < score < 80

    # None values
    score = market_regime_score()
    assert score == 0.0


def test_empty_series():
    empty = pd.Series(dtype=float)
    assert annualized_return(empty) == 0.0
    assert annualized_volatility(empty) == 0.0
    assert max_drawdown(empty) == 0.0
    assert value_at_risk(empty) == 0.0
