"""Financial calculations: Sharpe, drawdown, VaR, beta, correlation, regime score."""

import numpy as np
import pandas as pd
from scipy import stats

from config.settings import TRADING_DAYS


def daily_returns(prices: pd.Series) -> pd.Series:
    """Calculate daily percentage returns."""
    return prices.pct_change().dropna()


def cumulative_returns(returns: pd.Series) -> pd.Series:
    """Calculate cumulative returns from daily returns."""
    return (1 + returns).cumprod() - 1


def annualized_return(returns: pd.Series) -> float:
    """Annualized return from daily returns."""
    if returns.empty:
        return 0.0
    total = (1 + returns).prod()
    n_years = len(returns) / TRADING_DAYS
    if n_years <= 0:
        return 0.0
    return total ** (1 / n_years) - 1


def annualized_volatility(returns: pd.Series) -> float:
    """Annualized volatility from daily returns."""
    if returns.empty:
        return 0.0
    return returns.std() * np.sqrt(TRADING_DAYS)


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe ratio."""
    vol = annualized_volatility(returns)
    if vol == 0:
        return 0.0
    ann_ret = annualized_return(returns)
    return (ann_ret - risk_free_rate) / vol


def max_drawdown(prices: pd.Series) -> float:
    """Maximum drawdown as a negative fraction (e.g., -0.15 = -15%)."""
    if prices.empty:
        return 0.0
    peak = prices.cummax()
    dd = (prices - peak) / peak
    return dd.min()


def drawdown_series(prices: pd.Series) -> pd.Series:
    """Drawdown time series (negative fractions)."""
    if prices.empty:
        return pd.Series(dtype=float)
    peak = prices.cummax()
    return (prices - peak) / peak


def value_at_risk(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical VaR at given confidence level (negative number)."""
    if returns.empty:
        return 0.0
    return np.percentile(returns, (1 - confidence) * 100)


def beta(portfolio_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Portfolio beta relative to benchmark."""
    aligned = pd.concat([portfolio_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 2:
        return 1.0
    cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
    var_bench = cov[1, 1]
    if var_bench == 0:
        return 1.0
    return cov[0, 1] / var_bench


def correlation_matrix(prices_df: pd.DataFrame) -> pd.DataFrame:
    """Correlation matrix from a multi-column price DataFrame."""
    returns = prices_df.pct_change().dropna()
    return returns.corr()


def rolling_volatility(returns: pd.Series, window: int = 30) -> pd.Series:
    """Rolling annualized volatility."""
    return returns.rolling(window).std() * np.sqrt(TRADING_DAYS)


def rolling_returns(returns: pd.Series, window: int = 30) -> pd.Series:
    """Rolling cumulative return over window."""
    return returns.rolling(window).apply(lambda x: (1 + x).prod() - 1, raw=False)


def risk_contribution(weights: np.ndarray, cov_matrix: np.ndarray) -> np.ndarray:
    """Marginal risk contribution of each position."""
    port_vol = np.sqrt(weights @ cov_matrix @ weights)
    if port_vol == 0:
        return np.zeros_like(weights)
    marginal = (cov_matrix @ weights) / port_vol
    return weights * marginal / port_vol * 100


def market_regime_score(
    vix: float = None,
    yield_spread: float = None,
    momentum_pct_positive: float = None,
) -> float:
    """Composite market regime score 0-100 (higher = more risk-on).

    Components:
    - VIX: <15 = 33pts, 15-25 = 17pts, >25 = 0pts
    - Yield spread (10Y-2Y): positive = 33pts, flat/inverted = 0-17pts
    - Sector momentum: pct of sectors with positive 1M return * 34
    """
    score = 0.0

    if vix is not None:
        if vix < 15:
            score += 33
        elif vix < 25:
            score += 33 * (25 - vix) / 10
        # >25 = 0

    if yield_spread is not None:
        if yield_spread > 0.5:
            score += 33
        elif yield_spread > 0:
            score += 33 * (yield_spread / 0.5)
        elif yield_spread > -0.5:
            score += 17 * (yield_spread + 0.5) / 0.5
        # deeply inverted = 0

    if momentum_pct_positive is not None:
        score += 34 * momentum_pct_positive

    return min(100, max(0, score))
