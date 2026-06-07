"""
agents package – shared LLM factory.

Call ``get_llm()`` from any agent to obtain the configured chat model.
Switch providers by changing LLM_PROVIDER / MODEL_NAME in config.py or .env.
"""

from __future__ import annotations

import time
import logging

import config as _config

logger = logging.getLogger(__name__)


def get_llm(temperature: float = 0):
    """Return a LangChain chat model for the configured provider.

    Supported providers
    -------------------
    * ``gemini``     – Google Generative AI  (default, free tier)
    * ``openai``     – OpenAI / Azure
    * ``anthropic``  – Anthropic Claude
    """
    provider = _config.LLM_PROVIDER.lower().strip()
    model_name = _config.MODEL_NAME

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return _RateLimitWrapper(
            ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=_config.GOOGLE_API_KEY,
                temperature=temperature,
                max_retries=3,          # langchain internal retries
            )
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI          # type: ignore[import-untyped]

        return ChatOpenAI(
            model=model_name,
            api_key=_config.OPENAI_API_KEY,
            temperature=temperature,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic     # type: ignore[import-untyped]

        return ChatAnthropic(
            model_name=model_name,
            api_key=_config.ANTHROPIC_API_KEY,
            temperature=temperature,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. "
        "Set it to 'gemini', 'openai', or 'anthropic'."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rate-limit retry wrapper
# ─────────────────────────────────────────────────────────────────────────────

class _RateLimitWrapper:
    """Thin wrapper that retries on 429 / RESOURCE_EXHAUSTED with backoff.

    Gemini's free tier has per-minute (RPM) and per-day (RPD) quotas.
    Per-minute spikes are transient and resolve within ~30s.
    Per-day exhaustion (RPD=0) cannot be fixed by retrying — in that case
    this wrapper re-raises after ``_MAX_ATTEMPTS`` so the caller sees a
    clear error message.
    """

    _MAX_ATTEMPTS = 5
    _BASE_DELAY   = 30   # seconds (Google suggests "retry in ~21s")

    def __init__(self, llm) -> None:
        self._llm = llm

    def invoke(self, messages, **kwargs):
        last_exc = None
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            try:
                return self._llm.invoke(messages, **kwargs)
            except Exception as exc:
                exc_str = str(exc)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    # Check if it is a daily quota (unrecoverable today)
                    if "GenerateRequestsPerDayPerProjectPerModel" in exc_str:
                        raise RuntimeError(
                            f"\n\n❌ Daily quota exhausted for model '{_config.MODEL_NAME}'.\n"
                            "The free tier allows only a limited number of requests per day.\n\n"
                            "Options:\n"
                            "  1. Wait until tomorrow (quota resets at midnight UTC).\n"
                            "  2. Switch to a model with higher quotas in .env:\n"
                            "       MODEL_NAME=gemini-2.0-flash       # 1500 RPD free tier\n"
                            "       MODEL_NAME=gemini-2.0-flash-lite  # higher limits\n"
                            "  3. Use your OpenAI key instead:\n"
                            "       LLM_PROVIDER=openai\n"
                            "       MODEL_NAME=gpt-4o-mini\n"
                        ) from exc
                    # Transient RPM throttle – wait and retry
                    delay = self._BASE_DELAY * attempt
                    print(
                        f"  ⚠  Rate limited (429). Waiting {delay}s before retry "
                        f"{attempt}/{self._MAX_ATTEMPTS} …"
                    )
                    time.sleep(delay)
                    last_exc = exc
                else:
                    raise
        raise last_exc  # type: ignore[misc]

    # Forward attribute access to the underlying LLM so LangChain internals work
    def __getattr__(self, name: str):
        return getattr(self._llm, name)
