"""yfinance wrapper with Streamlit caching."""

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import streamlit as st
import yfinance as yf

from config.settings import (
    DEFAULT_BENCHMARK, PRICE_CACHE_TTL, SECTOR_CACHE_TTL,
    SECTOR_ETFS, VIX_TICKER, YIELD_CACHE_TTL, YIELD_TICKERS,
)
from data.database import save_price_history


@st.cache_data(ttl=PRICE_CACHE_TTL, show_spinner="Fetching prices...")
def fetch_current_prices(tickers: tuple[str, ...]) -> dict[str, dict]:
    """Fetch current price + daily change for multiple tickers.

    Returns dict of {ticker: {price, change, change_pct, name, currency}}.
    """
    result = {}
    if not tickers:
        return result

    for ticker_str in tickers:
        try:
            t = yf.Ticker(ticker_str)
            info = t.fast_info
            hist = t.history(period="2d")
            if hist.empty:
                continue

            current = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) >= 2 else current
            change = current - prev
            change_pct = (change / prev * 100) if prev != 0 else 0.0

            result[ticker_str] = {
                "price": current,
                "change": change,
                "change_pct": change_pct,
                "currency": getattr(info, "currency", "EUR"),
            }
        except Exception:
            continue

    return result


@st.cache_data(ttl=PRICE_CACHE_TTL, show_spinner="Loading price history...")
def fetch_price_history(
    ticker: str,
    period: str = "1y",
    start: str = None,
    end: str = None,
) -> pd.DataFrame:
    """Fetch OHLCV history for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        if start and end:
            df = t.history(start=start, end=end)
        else:
            df = t.history(period=period)
        if not df.empty:
            save_price_history(ticker, df)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=PRICE_CACHE_TTL, show_spinner="Loading portfolio history...")
def fetch_multi_history(
    tickers: tuple[str, ...],
    period: str = "1y",
) -> pd.DataFrame:
    """Fetch close prices for multiple tickers as a single DataFrame."""
    if not tickers:
        return pd.DataFrame()
    try:
        data = yf.download(list(tickers), period=period, group_by="ticker", progress=False)
        if data.empty:
            return pd.DataFrame()

        closes = pd.DataFrame()
        if len(tickers) == 1:
            closes[tickers[0]] = data["Close"]
        else:
            for ticker in tickers:
                if ticker in data.columns.get_level_values(0):
                    closes[ticker] = data[ticker]["Close"]
        return closes.dropna(how="all")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=PRICE_CACHE_TTL)
def fetch_benchmark_history(period: str = "1y") -> pd.DataFrame:
    """Fetch benchmark (MSCI World) price history."""
    return fetch_price_history(DEFAULT_BENCHMARK, period=period)


@st.cache_data(ttl=SECTOR_CACHE_TTL, show_spinner="Loading VIX data...")
def fetch_vix(period: str = "6mo") -> pd.DataFrame:
    return fetch_price_history(VIX_TICKER, period=period)


@st.cache_data(ttl=YIELD_CACHE_TTL, show_spinner="Loading yield data...")
def fetch_yield_curve() -> dict[str, float]:
    """Fetch current yield for each maturity."""
    result = {}
    for label, ticker in YIELD_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                result[label] = hist["Close"].iloc[-1]
        except Exception:
            continue
    return result


@st.cache_data(ttl=YIELD_CACHE_TTL)
def fetch_yield_curve_historical(months_ago: int = 3) -> dict[str, float]:
    """Fetch yield curve as of N months ago for comparison."""
    end = datetime.now() - timedelta(days=months_ago * 30)
    start = end - timedelta(days=7)
    result = {}
    for label, ticker in YIELD_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
            if not hist.empty:
                result[label] = hist["Close"].iloc[-1]
        except Exception:
            continue
    return result


@st.cache_data(ttl=SECTOR_CACHE_TTL, show_spinner="Loading sector data...")
def fetch_sector_performance(period: str = "1mo") -> dict[str, float]:
    """Fetch period return for each sector ETF."""
    result = {}
    for sector, ticker in SECTOR_ETFS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if len(hist) >= 2:
                ret = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                result[sector] = ret
        except Exception:
            continue
    return result


def validate_ticker(ticker: str) -> Optional[dict]:
    """Validate a ticker symbol and return basic info or None."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            return None
        info = t.fast_info
        return {
            "ticker": ticker,
            "currency": getattr(info, "currency", "N/A"),
            "last_price": hist["Close"].iloc[-1],
        }
    except Exception:
        return None
