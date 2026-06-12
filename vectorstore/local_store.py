from __future__ import annotations

import hashlib
import json
import os
import time
import math
from typing import Any

from config import (
    CACHE_DIR,
    EMBEDDING_MODEL,
    GOOGLE_API_KEY,
    OPENAI_API_KEY,
    LLM_PROVIDER,
)


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a * a for a in vec1))
    mag2 = math.sqrt(sum(b * b for b in vec2))
    if mag1 * mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


class LocalVectorStore:
    """A purely local vector store using JSON and native python cosine similarity.
    Replaces Pinecone to remove external dependencies and reduce latency.
    """

    def __init__(self) -> None:
        if LLM_PROVIDER == "openai":
            if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("your_"):
                raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings.")
            from langchain_openai import OpenAIEmbeddings
            self._embeddings = OpenAIEmbeddings(
                model=EMBEDDING_MODEL,
                openai_api_key=OPENAI_API_KEY,
            )
        else:
            if not GOOGLE_API_KEY or GOOGLE_API_KEY.startswith("your_"):
                raise RuntimeError("GOOGLE_API_KEY is required for Gemini embeddings.")
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model=EMBEDDING_MODEL,
                google_api_key=GOOGLE_API_KEY,
            )

    def index_code_map(
        self,
        code_map: list[dict],
        repo_name: str,
        *,
        batch_size: int = 80,
    ) -> int:
        if not code_map:
            return 0

        # Build text representations for embedding
        texts: list[str] = []
        for entry in code_map:
            text = (
                f"{entry['type']} {entry['name']} "
                f"in {entry['file']}: {entry.get('signature', '')}"
            )
            texts.append(text)

        # Embed in batches
        all_vectors: list[dict[str, Any]] = []
        from tenacity import retry, stop_after_attempt, wait_exponential

        @retry(stop=stop_after_attempt(10), wait=wait_exponential(multiplier=1, min=10, max=60))
        def _safe_embed(texts):
            return self._embeddings.embed_documents(texts)

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_entries = code_map[i : i + batch_size]

            embeddings = _safe_embed(batch_texts)

            for j, (vec, entry) in enumerate(zip(embeddings, batch_entries)):
                vec_id = self._make_id(repo_name, entry, i + j)
                all_vectors.append(
                    {
                        "id": vec_id,
                        "values": vec,
                        "metadata": {
                            "name": entry.get("name", ""),
                            "type": entry.get("type", ""),
                            "file": entry.get("file", ""),
                            "line": entry.get("line", 0),
                            "signature": entry.get("signature", ""),
                            "repo": repo_name,
                        },
                    }
                )

            # Small delay between batches to respect rate limits
            if i + batch_size < len(texts):
                time.sleep(2.0)

        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(self._local_index_path(repo_name), "w", encoding="utf-8") as fh:
            json.dump(all_vectors, fh)
            
        print(f"  ↳ Indexed {len(all_vectors)} code entries into Local Store")
        return len(all_vectors)

    # ──────────────────── search ────────────────────────────

    def search(
        self,
        query: str,
        repo_name: str,
        top_k: int = 15,
    ) -> list[dict]:
        path = self._local_index_path(repo_name)
        if not os.path.isfile(path):
            return []
            
        with open(path, "r", encoding="utf-8") as fh:
            all_vectors = json.load(fh)

        if not all_vectors:
            return []

        query_vec = self._embeddings.embed_query(query)

        # Compute cosine similarity for all vectors
        scored: list[tuple[float, dict]] = []
        for item in all_vectors:
            score = _cosine_similarity(query_vec, item["values"])
            scored.append((score, item["metadata"]))

        # Sort and take top k
        scored.sort(key=lambda x: x[0], reverse=True)
        
        hits: list[dict] = []
        for score, meta in scored[:top_k]:
            hits.append(
                {
                    "name": meta.get("name", ""),
                    "type": meta.get("type", ""),
                    "file": meta.get("file", ""),
                    "line": meta.get("line", 0),
                    "signature": meta.get("signature", ""),
                    "score": score,
                }
            )
        return hits

    # ──────────────────── cache helpers ─────────────────────

    def is_cached(self, repo_name: str, commit_hash: str) -> bool:
        cache_file = self._cache_path(repo_name)
        if not os.path.isfile(cache_file):
            return False
        with open(cache_file, "r") as fh:
            cached = json.load(fh)
        if cached.get("commit") != commit_hash:
            return False
        return os.path.isfile(self._local_index_path(repo_name))

    def save_cache(self, repo_name: str, commit_hash: str, count: int) -> None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = self._cache_path(repo_name)
        with open(cache_file, "w") as fh:
            json.dump({"commit": commit_hash, "vectors": count}, fh)

    # ──────────────────── private ───────────────────────────

    @staticmethod
    def _make_id(repo_name: str, entry: dict, idx: int) -> str:
        raw = f"{repo_name}/{entry.get('file', '')}/{entry.get('name', '')}/{idx}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _cache_path(repo_name: str) -> str:
        safe_name = repo_name.replace("/", "_")
        return os.path.join(CACHE_DIR, f"{safe_name}_index.json")

    @staticmethod
    def _local_index_path(repo_name: str) -> str:
        safe_name = repo_name.replace("/", "_")
        return os.path.join(CACHE_DIR, f"{safe_name}_local_vectors.json")
