"""
Agentic Go Contributor – Configuration

Change MODEL_NAME or LLM_PROVIDER to switch LLM backends.
All sensitive keys are loaded from environment / .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")        # gemini | openai | anthropic
MODEL_NAME: str   = os.getenv("MODEL_NAME", "gemini-2.0-flash") # model identifier

# ────────────────────────────────────────────────────────────
# API keys
# ────────────────────────────────────────────────────────────
GOOGLE_API_KEY:    str = os.getenv("GOOGLE_API_KEY", "")
OPENAI_API_KEY:    str = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN:      str = os.getenv("GITHUB_TOKEN", "")

PINECONE_API_KEY:    str = os.getenv("PINECONE_API_KEY", "")
_base_index = os.getenv("PINECONE_INDEX_NAME", "go-contributor-v2")
PINECONE_INDEX_NAME: str = f"{_base_index}-openai" if LLM_PROVIDER == "openai" else _base_index
PINECONE_CLOUD:      str = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION:     str = os.getenv("PINECONE_REGION", "us-east-1")

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")
EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "3072"))

MAX_RETRIES:       int = int(os.getenv("MAX_RETRIES", "3"))
MAX_CONTEXT_FILES: int = int(os.getenv("MAX_CONTEXT_FILES", "10"))

REPOS_DIR:  str = os.getenv("REPOS_DIR", "repos")
CACHE_DIR:  str = os.getenv("CACHE_DIR", ".cache")
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")
