"""Provider-agnostic LLM client for the AI Financial Advisor.

Supports Anthropic (Claude), OpenAI (GPT), and Google (Gemini).
Provider and model configurable via environment variables.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int


def _get_provider() -> str:
    return os.getenv("ADVISOR_LLM_PROVIDER", "google").lower()


def _get_model(provider: str) -> str:
    model = os.getenv("ADVISOR_LLM_MODEL")
    if model:
        return model
    defaults = {
        "google": "gemini-2.5-flash",
        "anthropic": "claude-sonnet-4-20250514",
        "openai": "gpt-4o",
    }
    return defaults.get(provider, "gemini-2.5-flash")


def _call_anthropic(system_prompt: str, user_prompt: str, model: str) -> LLMResponse:
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return LLMResponse(
        text=response.content[0].text,
        model=model,
        provider="anthropic",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


def _call_openai(system_prompt: str, user_prompt: str, model: str) -> LLMResponse:
    from openai import OpenAI
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return LLMResponse(
        text=response.choices[0].message.content,
        model=model,
        provider="openai",
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens,
    )


def _call_google(system_prompt: str, user_prompt: str, model: str) -> LLMResponse:
    from google import genai

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=16384,
        ),
    )
    usage = response.usage_metadata
    return LLMResponse(
        text=response.text,
        model=model,
        provider="google",
        input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
        output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
    )


_PROVIDERS = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "google": _call_google,
}


def generate(
    system_prompt: str,
    user_prompt: str,
    provider: str = None,
    model: str = None,
) -> LLMResponse:
    """Generate a response from the configured LLM provider.

    Args:
        system_prompt: System/instruction prompt.
        user_prompt: User message with portfolio context.
        provider: Override provider (anthropic/openai/google).
        model: Override model name.

    Returns:
        LLMResponse with text, token usage, and metadata.

    Raises:
        ValueError: If provider is not supported.
        Exception: If the API call fails.
    """
    provider = provider or _get_provider()
    model = model or _get_model(provider)

    call_fn = _PROVIDERS.get(provider)
    if not call_fn:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Supported: {', '.join(_PROVIDERS.keys())}"
        )

    logger.info("LLM call: provider=%s model=%s", provider, model)
    response = call_fn(system_prompt, user_prompt, model)
    logger.info(
        "LLM response: %d input tokens, %d output tokens",
        response.input_tokens, response.output_tokens,
    )
    return response
