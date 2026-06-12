from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from config import (
    CACHE_DIR,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    GOOGLE_API_KEY,
    PINECONE_API_KEY,
    PINECONE_CLOUD,
    PINECONE_INDEX_NAME,
    PINECONE_REGION,
    VECTORSTORE_BACKEND,
)


class CodeVectorStore:

    def __init__(self) -> None:
        from config import LLM_PROVIDER

        self._local = VECTORSTORE_BACKEND.lower() == "local" or LLM_PROVIDER.lower() == "mock"
        if self._local:
            self._pc = None
            self._embeddings = None
            self._index = None
            return

        if not PINECONE_API_KEY or PINECONE_API_KEY.startswith("your_"):
            raise RuntimeError(
                "PINECONE_API_KEY is required when VECTORSTORE_BACKEND=pinecone. "
                "Set it in .env or use VECTORSTORE_BACKEND=local for offline tests."
            )

        from pinecone import Pinecone, ServerlessSpec          # type: ignore[import-untyped]
        from config import OPENAI_API_KEY
        
        self._pc = Pinecone(api_key=PINECONE_API_KEY)
        
        if LLM_PROVIDER == "openai":
            if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("your_"):
                raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings.")
            from langchain_openai import OpenAIEmbeddings
            self._embeddings = OpenAIEmbeddings(
                model="text-embedding-3-large", # 3072 dimensions
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

        # Create index if it doesn't exist
        existing = [idx.name for idx in self._pc.list_indexes()]
        if PINECONE_INDEX_NAME not in existing:
            print(f"  ↳ Creating Pinecone index '{PINECONE_INDEX_NAME}' …")
            self._pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=EMBEDDING_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
            )
            # Wait for index to be ready
            while not self._pc.describe_index(PINECONE_INDEX_NAME).status.get("ready"):
                time.sleep(1)

        self._index = self._pc.Index(PINECONE_INDEX_NAME)

    def index_code_map(
        self,
        code_map: list[dict],
        repo_name: str,
        *,
        batch_size: int = 80,
    ) -> int:
        if not code_map:
            return 0
        if self._local:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(self._local_index_path(repo_name), "w", encoding="utf-8") as fh:
                json.dump(code_map, fh)
            print(f"  ↳ Indexed {len(code_map)} code entries into local store")
            return len(code_map)

        # Build text representations for embedding
        texts: list[str] = []
        for entry in code_map:
            text = (
                f"{entry['type']} {entry['name']} "
                f"in {entry['file']}: {entry.get('signature', '')}"
            )
            texts.append(text)

        # Embed in batches (rate-limit friendly)
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
                            "name": entry["name"],
                            "type": entry["type"],
                            "file": entry["file"],
                            "line": entry.get("line", 0),
                            "signature": entry.get("signature", ""),
                            "repo": repo_name,
                        },
                    }
                )

            # Small delay between batches to respect rate limits
            if i + batch_size < len(texts):
                time.sleep(2.0)

        # Upsert into Pinecone (batch of 100 max)
        namespace = repo_name.replace("/", "_")
        for i in range(0, len(all_vectors), 100):
            self._index.upsert(
                vectors=all_vectors[i : i + 100],
                namespace=namespace,
            )

        print(f"  ↳ Indexed {len(all_vectors)} code entries into Pinecone")
        return len(all_vectors)

    # ──────────────────── search ────────────────────────────

    def search(
        self,
        query: str,
        repo_name: str,
        top_k: int = 15,
    ) -> list[dict]:
        if self._local:
            return self._local_search(query, repo_name, top_k)

        query_vec = self._embeddings.embed_query(query)
        namespace = repo_name.replace("/", "_")

        results = self._index.query(
            vector=query_vec,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True,
        )

        hits: list[dict] = []
        matches = results.get("matches", []) if isinstance(results, dict) else getattr(results, "matches", [])
        for match in matches:
            meta = match.get("metadata", {}) if isinstance(match, dict) else getattr(match, "metadata", {})
            score = match.get("score", 0.0) if isinstance(match, dict) else getattr(match, "score", 0.0)
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
        if self._local:
            return os.path.isfile(self._local_index_path(repo_name))
        return True

    def save_cache(self, repo_name: str, commit_hash: str, count: int) -> None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = self._cache_path(repo_name)
        with open(cache_file, "w") as fh:
            json.dump({"commit": commit_hash, "vectors": count}, fh)

    # ──────────────────── private ───────────────────────────

    @staticmethod
    def _make_id(repo_name: str, entry: dict, idx: int) -> str:
        raw = f"{repo_name}/{entry['file']}/{entry['name']}/{idx}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _cache_path(repo_name: str) -> str:
        safe_name = repo_name.replace("/", "_")
        return os.path.join(CACHE_DIR, f"{safe_name}_index.json")

    @staticmethod
    def _local_index_path(repo_name: str) -> str:
        safe_name = repo_name.replace("/", "_")
        return os.path.join(CACHE_DIR, f"{safe_name}_local_code_map.json")

    def _local_search(self, query: str, repo_name: str, top_k: int) -> list[dict]:
        path = self._local_index_path(repo_name)
        if not os.path.isfile(path):
            return []
        with open(path, "r", encoding="utf-8") as fh:
            entries = json.load(fh)

        query_tokens = _tokens(query)
        scored: list[tuple[int, dict]] = []
        for entry in entries:
            haystack = " ".join(
                str(entry.get(key, ""))
                for key in ("name", "type", "file", "signature")
            )
            score = len(query_tokens & _tokens(haystack))
            if score:
                scored.append((score, entry))

        if not scored:
            scored = [(1, entry) for entry in entries[:top_k]]

        scored.sort(key=lambda item: item[0], reverse=True)
        hits: list[dict] = []
        for score, entry in scored[:top_k]:
            hits.append({
                "name": entry.get("name", ""),
                "type": entry.get("type", ""),
                "file": entry.get("file", ""),
                "line": entry.get("line", 0),
                "signature": entry.get("signature", ""),
                "score": float(score),
            })
        return hits


def _tokens(text: str) -> set[str]:
    import re

    return {
        token.lower()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
    }
