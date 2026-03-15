"""AI Financial Advisor engine.

Assembles portfolio context from existing data sources and generates
AI-powered analysis, recommendations, and opportunity detection.
"""

import hashlib
import json
import logging
from datetime import date

import yfinance as yf

from config.advisor_prompts import (
    MORNING_NOTE_PROMPT,
    OPPORTUNITY_SCREEN_PROMPT,
    PORTFOLIO_REVIEW_PROMPT,
    QA_SYSTEM_PROMPT,
    REBALANCE_PROMPT,
    SYSTEM_PROMPT,
)
from config.settings import (
    ADVISOR_CACHE_DAILY_TTL,
    ADVISOR_CACHE_OPPORTUNITY_TTL,
    ADVISOR_CACHE_REBALANCE_TTL,
    ADVISOR_LLM_PROVIDER,
    ADVISOR_QA_MODEL,
    ADVISOR_QA_PROVIDER,
    BENCHMARK_INDICES,
    CURRENCY_OVERRIDES,
    FX_PAIRS,
    PRICE_SCALE_FACTORS,
    THEME_ETFS,
    THEME_TICKER_GROUPS,
    VIX_TICKER,
)
from data.database import (
    get_cached_advisor_response,
    get_latest_advisor_response,
    get_morningstar_cache,
    get_positions,
    get_regime_history,
    save_advisor_response,
)
from data.llm_client import generate as llm_generate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_portfolio_context() -> str:
    """Assemble all portfolio data into a text context for the LLM prompt.

    Calls yfinance directly (no Streamlit cache) so it works in CLI and UI.
    """
    positions = get_positions()
    if positions.empty:
        return "No positions found in the portfolio."

    tickers = positions["ticker"].tolist()

    # Fetch current prices
    prices = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if hist.empty:
                continue
            current = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) >= 2 else current

            # Apply price scale factor (e.g. wrong share class)
            scale = PRICE_SCALE_FACTORS.get(ticker, 1.0)
            current *= scale
            prev *= scale

            change_pct = ((current - prev) / prev * 100) if prev != 0 else 0.0

            currency = getattr(t.fast_info, "currency", None)
            currency = CURRENCY_OVERRIDES.get(ticker, currency) or "EUR"

            prices[ticker] = {
                "price": current,
                "change_pct": round(change_pct, 2),
                "currency": currency,
            }
        except Exception:
            continue

    # FX rates
    fx_rates = {"EUR": 1.0}
    for pair_name, pair_ticker in FX_PAIRS.items():
        try:
            t = yf.Ticker(pair_ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                fx_rates[pair_name.split("/")[1]] = 1.0 / hist["Close"].iloc[-1]
        except Exception:
            pass
    fx_rates["GBp"] = fx_rates.get("GBP", 1.17) / 100.0

    # Build position lines
    lines = [f"## Portfolio Positions (as of {date.today().isoformat()})"]
    lines.append("| Name | Ticker | Units | Cost Basis (EUR) | Current Price | Currency | Day Change | Market Value (EUR) | P&L (EUR) | P&L % |")
    lines.append("|------|--------|-------|-----------------|---------------|----------|-----------|-------------------|-----------|-------|")

    total_value = 0.0
    total_cost = 0.0
    position_data = []

    for _, pos in positions.iterrows():
        ticker = pos["ticker"]
        p = prices.get(ticker)
        if not p:
            continue

        price = p["price"]
        currency = p["currency"]
        fx_rate = fx_rates.get(currency, 1.0)
        value_eur = pos["units"] * price * fx_rate
        cost = pos["cost_basis"]
        pnl = value_eur - cost
        pnl_pct = (pnl / cost * 100) if cost != 0 else 0.0

        total_value += value_eur
        total_cost += cost

        position_data.append({
            "name": pos["name"],
            "ticker": ticker,
            "units": pos["units"],
            "cost": cost,
            "value_eur": value_eur,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "sector": pos["sector"],
        })

        lines.append(
            f"| {pos['name'][:35]} | {ticker} | {pos['units']:.2f} | "
            f"{cost:,.0f} | {price:.2f} | {currency} | {p['change_pct']:+.2f}% | "
            f"{value_eur:,.0f} | {pnl:+,.0f} | {pnl_pct:+.1f}% |"
        )

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost != 0 else 0.0
    lines.append(f"\n**Total Portfolio Value: EUR {total_value:,.0f}** | "
                 f"Cost: EUR {total_cost:,.0f} | "
                 f"P&L: EUR {total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)")

    # Theme allocations
    lines.append("\n## Theme Allocations")
    for theme, theme_tickers in THEME_TICKER_GROUPS.items():
        theme_value = sum(
            pd.get("value_eur", 0) for pd in position_data
            if pd["ticker"] in theme_tickers
        )
        weight = (theme_value / total_value * 100) if total_value > 0 else 0
        lines.append(f"- **{theme}**: EUR {theme_value:,.0f} ({weight:.1f}%)")

    # Market context: VIX
    lines.append("\n## Market Context")
    try:
        vix = yf.Ticker(VIX_TICKER)
        vix_hist = vix.history(period="5d")
        if not vix_hist.empty:
            vix_level = vix_hist["Close"].iloc[-1]
            lines.append(f"- **VIX (Fear Index)**: {vix_level:.1f}")
    except Exception:
        pass

    # Benchmark indices
    for name, ticker in BENCHMARK_INDICES.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                current = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2] if len(hist) >= 2 else current
                ch = ((current - prev) / prev * 100) if prev != 0 else 0.0
                lines.append(f"- **{name}**: {current:,.1f} ({ch:+.2f}% today)")
        except Exception:
            continue

    # Theme ETF momentum (1M)
    lines.append("\n## Theme ETF Momentum (1-Month Returns)")
    for theme, etf in THEME_ETFS.items():
        try:
            t = yf.Ticker(etf)
            hist = t.history(period="1mo")
            if len(hist) >= 2:
                ret = ((hist["Close"].iloc[-1] / hist["Close"].iloc[0]) - 1) * 100
                lines.append(f"- **{theme}** ({etf}): {ret:+.1f}%")
        except Exception:
            continue

    # Regime history
    regime = get_regime_history(limit=5)
    if not regime.empty:
        lines.append("\n## Recent Market Regime Scores")
        for _, r in regime.iterrows():
            lines.append(
                f"- {r['date']}: Score {r['score']:.0f} "
                f"(VIX: {r.get('vix', 'N/A')}, "
                f"Yield Spread: {r.get('yield_spread', 'N/A')})"
            )

    # Morningstar ratings
    ms = get_morningstar_cache()
    if not ms.empty:
        lines.append("\n## Morningstar Fund Ratings")
        for _, r in ms.iterrows():
            stars = r.get("star_rating", "N/A")
            prev = r.get("previous_star_rating", "N/A")
            change = ""
            if stars and prev and stars != "N/A" and prev != "N/A":
                try:
                    diff = int(stars) - int(prev)
                    if diff != 0:
                        change = f" (was {prev}, {'upgraded' if diff > 0 else 'downgraded'})"
                except (ValueError, TypeError):
                    pass
            lines.append(
                f"- {r.get('fund_name', r['isin'])}: "
                f"{stars} stars{change} | {r.get('medalist_rating', 'N/A')} | "
                f"{r.get('category', 'N/A')}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt hash for caching
# ---------------------------------------------------------------------------

def _hash_prompt(response_type: str) -> str:
    """Create a date-based hash for caching (same type on same day = same hash)."""
    key = f"{response_type}:{date.today().isoformat()}"
    return hashlib.md5(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Analysis generators
# ---------------------------------------------------------------------------

def _generate_or_cached(
    response_type: str,
    prompt_template: str,
    force_refresh: bool,
) -> dict:
    """Show last cached response on load; only call LLM on refresh.

    Returns dict with keys: text, model, provider, cached, created_at.
    """
    if not force_refresh:
        last = get_latest_advisor_response(response_type)
        if last:
            return {
                "text": last["text"],
                "cached": True,
                "model": last["model"],
                "provider": last["provider"],
                "created_at": last["created_at"],
            }

    # Generate fresh analysis
    prompt_hash = _hash_prompt(response_type)
    context = build_portfolio_context()
    user_prompt = prompt_template.format(portfolio_context=context)

    response = llm_generate(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)

    save_advisor_response(
        response_type=response_type,
        prompt_hash=prompt_hash,
        response_text=response.text,
        model_used=response.model,
        provider=response.provider,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )

    return {
        "text": response.text,
        "cached": False,
        "model": response.model,
        "provider": response.provider,
        "created_at": None,
    }


def generate_daily_analysis(force_refresh: bool = False) -> dict:
    """Generate or retrieve cached daily portfolio analysis."""
    return _generate_or_cached("daily_analysis", MORNING_NOTE_PROMPT, force_refresh)


def generate_rebalance_analysis(force_refresh: bool = False) -> dict:
    """Generate portfolio rebalancing recommendations."""
    return _generate_or_cached("rebalance", REBALANCE_PROMPT, force_refresh)


def generate_opportunity_scan(force_refresh: bool = False) -> dict:
    """Scan for investment opportunities."""
    return _generate_or_cached("opportunity", OPPORTUNITY_SCREEN_PROMPT, force_refresh)


def generate_portfolio_review(force_refresh: bool = False) -> dict:
    """Generate a comprehensive portfolio review."""
    response_type = "portfolio_review"
    prompt_hash = _hash_prompt(response_type)

    if not force_refresh:
        cached = get_cached_advisor_response(
            response_type, prompt_hash, ADVISOR_CACHE_REBALANCE_TTL
        )
        if cached:
            return {"text": cached, "cached": True, "model": "", "provider": ""}

    context = build_portfolio_context()
    user_prompt = PORTFOLIO_REVIEW_PROMPT.format(portfolio_context=context)

    response = llm_generate(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)

    save_advisor_response(
        response_type=response_type,
        prompt_hash=prompt_hash,
        response_text=response.text,
        model_used=response.model,
        provider=response.provider,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )

    return {
        "text": response.text,
        "cached": False,
        "model": response.model,
        "provider": response.provider,
    }


def ask_advisor(question: str) -> dict:
    """Ask a free-form question to the AI advisor (no caching)."""
    context = build_portfolio_context()
    system = QA_SYSTEM_PROMPT.format(portfolio_context=context)

    # Use QA-specific provider/model if configured
    qa_provider = ADVISOR_QA_PROVIDER or None
    qa_model = ADVISOR_QA_MODEL or None

    response = llm_generate(
        system_prompt=system,
        user_prompt=question,
        provider=qa_provider,
        model=qa_model,
    )

    save_advisor_response(
        response_type="qa",
        prompt_hash=hashlib.md5(question.encode()).hexdigest(),
        response_text=response.text,
        model_used=response.model,
        provider=response.provider,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )

    return {
        "text": response.text,
        "cached": False,
        "model": response.model,
        "provider": response.provider,
    }
