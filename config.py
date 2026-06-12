import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=False)

# ────────────────────────────────────────────────────────────
# LLM – change these two values to swap models at any time
# ────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")        # gemini | openai | anthropic
MODEL_NAME: str   = os.getenv("MODEL_NAME", "gemini-2.0-flash") # model identifier

# ────────────────────────────────────────────────────────────
# API keys
# ────────────────────────────────────────────────────────────
GOOGLE_API_KEY:    str = os.getenv("GOOGLE_API_KEY", "")
OPENAI_API_KEY:    str = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN:      str = os.getenv("GITHUB_TOKEN", "")          # optional – raises rate limit

# Vector store is now fully local, no external service config needed.

# Embedding model – gemini-embedding-001 is the stable Google model (3072 dims).
# text-embedding-004 is NOT available on the v1beta API endpoint used by langchain-google-genai.
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")
EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "3072"))

# ────────────────────────────────────────────────────────────
# Agent behaviour
# ────────────────────────────────────────────────────────────
MAX_RETRIES:       int = int(os.getenv("MAX_RETRIES", "3"))
MAX_CONTEXT_FILES: int = int(os.getenv("MAX_CONTEXT_FILES", "10"))

# ────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────
REPOS_DIR:  str = os.getenv("REPOS_DIR", "repos")
CACHE_DIR:  str = os.getenv("CACHE_DIR", ".cache")
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")
