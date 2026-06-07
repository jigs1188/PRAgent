"""
agents package – shared LLM factory.

Call ``get_llm()`` from any agent to obtain the configured chat model.
Switch providers by changing LLM_PROVIDER / MODEL_NAME in config.py or .env.
"""

from __future__ import annotations

from config import (
    LLM_PROVIDER,
    MODEL_NAME,
    GOOGLE_API_KEY,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
)


def get_llm(temperature: float = 0):
    """Return a LangChain chat model for the configured provider.

    Supported providers
    -------------------
    * ``gemini``     – Google Generative AI  (default, free tier)
    * ``openai``     – OpenAI / Azure
    * ``anthropic``  – Anthropic Claude
    """
    provider = LLM_PROVIDER.lower().strip()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            google_api_key=GOOGLE_API_KEY,
            temperature=temperature,
            max_retries=10,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI          # type: ignore[import-untyped]

        return ChatOpenAI(
            model=MODEL_NAME,
            api_key=OPENAI_API_KEY,
            temperature=temperature,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic     # type: ignore[import-untyped]

        return ChatAnthropic(
            model_name=MODEL_NAME,
            api_key=ANTHROPIC_API_KEY,
            temperature=temperature,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. "
        "Set it to 'gemini', 'openai', or 'anthropic'."
    )
