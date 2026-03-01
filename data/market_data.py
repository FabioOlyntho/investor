"""yfinance wrapper with Streamlit caching."""

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import streamlit as st
import yfinance as yf

from config.settings import (
    BENCHMARK_INDICES, DEFAULT_BENCHMARK, FX_PAIRS, FUND_ISIN_MAP,
    MORNINGSTAR_CACHE_TTL, PRICE_CACHE_TTL, SECTOR_CACHE_TTL,
    SECTOR_ETFS, THEME_ETFS, VIX_TICKER, YIELD_CACHE_TTL, YIELD_TICKERS,
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
            hist = t.history(period="5d")
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
            df.index = df.index.tz_localize(None)
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
        if not closes.empty and closes.index.tz is not None:
            closes.index = closes.index.tz_localize(None)
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


@st.cache_data(ttl=PRICE_CACHE_TTL, show_spinner="Fetching FX rates...")
def fetch_fx_rates() -> dict[str, float]:
    """Fetch EUR exchange rates. Returns {currency: rate_to_eur}.

    E.g. {'USD': 0.92, 'GBP': 1.17, 'GBp': 0.0117, 'CHF': 1.05, 'EUR': 1.0}
    GBp = pence, divide GBP rate by 100.
    """
    rates = {"EUR": 1.0}
    fx_pairs = {"USD": "EURUSD=X", "GBP": "EURGBP=X", "CHF": "EURCHF=X"}
    for currency, pair in fx_pairs.items():
        try:
            t = yf.Ticker(pair)
            hist = t.history(period="5d")
            if not hist.empty:
                # EURUSD=X gives how many USD per 1 EUR, so 1/rate = EUR per 1 USD
                rates[currency] = 1.0 / hist["Close"].iloc[-1]
        except Exception:
            # Fallback approximations
            fallbacks = {"USD": 0.92, "GBP": 1.17, "CHF": 1.05}
            rates[currency] = fallbacks.get(currency, 1.0)
    # GBp (pence) = GBP / 100
    rates["GBp"] = rates.get("GBP", 1.17) / 100.0
    return rates


def convert_to_eur(value: float, currency: str, fx_rates: dict[str, float]) -> float:
    """Convert a value from its native currency to EUR."""
    if currency is None or currency == "EUR":
        return value
    rate = fx_rates.get(currency, 1.0)
    return value * rate


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


# --- Benchmark Indices ---

@st.cache_data(ttl=PRICE_CACHE_TTL, show_spinner="Loading index data...")
def fetch_benchmark_indices() -> dict[str, dict]:
    """Fetch current value and daily change for major indices.

    Returns {name: {value, change, change_pct}} e.g.
    {"S&P 500": {value: 5200.5, change: 25.3, change_pct: 0.49}}
    """
    result = {}
    for name, ticker in BENCHMARK_INDICES.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if len(hist) >= 2:
                current = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                change = current - prev
                change_pct = (change / prev * 100) if prev != 0 else 0.0
                result[name] = {
                    "value": current,
                    "change": change,
                    "change_pct": change_pct,
                }
        except Exception:
            continue
    return result


def fetch_benchmark_indices_no_cache() -> dict[str, dict]:
    """Fetch major index data without Streamlit cache."""
    result = {}
    for name, ticker in BENCHMARK_INDICES.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if len(hist) >= 2:
                current = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                change = current - prev
                change_pct = (change / prev * 100) if prev != 0 else 0.0
                result[name] = {
                    "value": current,
                    "change": change,
                    "change_pct": change_pct,
                }
        except Exception:
            continue
    return result


# --- Theme Performance ---

@st.cache_data(ttl=SECTOR_CACHE_TTL, show_spinner="Loading theme data...")
def fetch_theme_performance(period: str = "1mo") -> dict[str, float]:
    """Fetch period return for each theme ETF.

    Returns {etf_ticker: return_pct} e.g. {"EWY": -3.2, "URA": 5.1}
    """
    result = {}
    for theme, ticker in THEME_ETFS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if len(hist) >= 2:
                ret = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                result[ticker] = ret
        except Exception:
            continue
    return result


# --- FX Daily Changes ---

@st.cache_data(ttl=PRICE_CACHE_TTL, show_spinner="Loading FX data...")
def fetch_fx_daily_changes() -> dict[str, dict]:
    """Fetch daily rate and change for FX pairs.

    Returns {pair_label: {rate, change_pct}} e.g. {"EUR/USD": {rate: 1.08, change_pct: 0.3}}
    """
    result = {}
    for label, ticker in FX_PAIRS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if len(hist) >= 2:
                current = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                change_pct = ((current - prev) / prev) * 100
                result[label] = {"rate": current, "change_pct": change_pct}
        except Exception:
            continue
    return result


# --- Morningstar Ratings ---

@st.cache_data(ttl=MORNINGSTAR_CACHE_TTL, show_spinner="Loading Morningstar ratings...")
def fetch_morningstar_ratings() -> list[dict]:
    """Fetch star ratings for all portfolio funds via mstarpy.

    Returns list of dicts with isin, fund_name, star_rating,
    previous_star_rating, medalist_rating, category, risk_rating.
    """
    return _fetch_morningstar_ratings_impl()


def _fetch_morningstar_ratings_impl() -> list[dict]:
    """Implementation shared between cached and no-cache variants."""
    results = []
    try:
        from mstarpy import Funds
    except ImportError:
        return results

    for ticker, isin in FUND_ISIN_MAP.items():
        try:
            fund = Funds(term=isin)
            name = fund.name

            star_rating = None
            previous_star_rating = None
            medalist_rating = None
            risk_rating = None
            category = None

            # dataPoint() takes one field at a time, returns {field: {value, properties}}
            try:
                dp = fund.dataPoint("fundStarRating")
                info = dp.get("fundStarRating", {})
                star_rating = int(info["value"]) if info.get("value") else None
                prev = info.get("properties", {}).get("previous", {})
                if isinstance(prev, dict) and prev.get("value") is not None:
                    previous_star_rating = int(prev["value"])
            except Exception:
                pass

            try:
                dp = fund.dataPoint("medalistRating")
                info = dp.get("medalistRating", {})
                medalist_rating = str(info["value"]) if info.get("value") else None
            except Exception:
                pass

            try:
                dp = fund.dataPoint("morningstarRiskRating")
                info = dp.get("morningstarRiskRating", {})
                risk_rating = str(info["value"]) if info.get("value") else None
            except Exception:
                pass

            try:
                dp = fund.dataPoint("morningstarCategory")
                info = dp.get("morningstarCategory", {})
                category = str(info["value"]) if info.get("value") else None
            except Exception:
                pass

            results.append({
                "ticker": ticker,
                "isin": isin,
                "fund_name": name if name else isin,
                "star_rating": star_rating,
                "previous_star_rating": previous_star_rating,
                "medalist_rating": medalist_rating,
                "category": category,
                "risk_rating": risk_rating,
            })
        except Exception:
            continue

    return results


# --- No-cache variants for CLI ---

def fetch_theme_performance_no_cache(period: str = "1mo") -> dict[str, float]:
    """Fetch theme ETF performance without Streamlit cache."""
    result = {}
    for theme, ticker in THEME_ETFS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if len(hist) >= 2:
                ret = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                result[ticker] = ret
        except Exception:
            continue
    return result


def fetch_fx_daily_changes_no_cache() -> dict[str, dict]:
    """Fetch FX changes without Streamlit cache."""
    result = {}
    for label, ticker in FX_PAIRS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if len(hist) >= 2:
                current = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                change_pct = ((current - prev) / prev) * 100
                result[label] = {"rate": current, "change_pct": change_pct}
        except Exception:
            continue
    return result


def fetch_morningstar_ratings_no_cache() -> list[dict]:
    """Fetch Morningstar ratings without Streamlit cache."""
    return _fetch_morningstar_ratings_impl()
