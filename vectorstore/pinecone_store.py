"""
Pinecone-backed vector store for the repository code map.

Stores function/struct/interface signatures as embeddings so that
the Context Retriever can find relevant code by semantic search.
"""

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
)


class CodeVectorStore:

    def __init__(self) -> None:
        from pinecone import Pinecone, ServerlessSpec          # type: ignore[import-untyped]
        from config import LLM_PROVIDER, OPENAI_API_KEY
        
        self._pc = Pinecone(api_key=PINECONE_API_KEY)
        
        if LLM_PROVIDER == "openai":
            from langchain_openai import OpenAIEmbeddings
            self._embeddings = OpenAIEmbeddings(
                model="text-embedding-3-large", # 3072 dimensions
                openai_api_key=OPENAI_API_KEY,
            )
        else:
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
        """Embed and upsert code-map entries into Pinecone.

        Uses ``repo_name`` as the Pinecone namespace so multiple
        repositories can coexist in a single index.

        Returns the number of vectors upserted.
        """
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
        """Semantic search the code map.

        Returns a list of ``{name, type, file, line, signature, score}``
        dicts sorted by relevance.
        """
        query_vec = self._embeddings.embed_query(query)
        namespace = repo_name.replace("/", "_")

        results = self._index.query(
            vector=query_vec,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True,
        )

        hits: list[dict] = []
        for match in results.get("matches", []):
            meta = match.get("metadata", {})
            hits.append(
                {
                    "name": meta.get("name", ""),
                    "type": meta.get("type", ""),
                    "file": meta.get("file", ""),
                    "line": meta.get("line", 0),
                    "signature": meta.get("signature", ""),
                    "score": match.get("score", 0.0),
                }
            )
        return hits

    # ──────────────────── cache helpers ─────────────────────

    def is_cached(self, repo_name: str, commit_hash: str) -> bool:
        """Check if this repo+commit has already been indexed."""
        cache_file = self._cache_path(repo_name)
        if not os.path.isfile(cache_file):
            return False
        with open(cache_file, "r") as fh:
            cached = json.load(fh)
        return cached.get("commit") == commit_hash

    def save_cache(self, repo_name: str, commit_hash: str, count: int) -> None:
        """Save indexing metadata to local cache."""
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
