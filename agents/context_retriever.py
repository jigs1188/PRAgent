"""
Context Retriever Agent

Combines:
1. **Pinecone semantic search** – finds relevant symbols from the code map.
2. **Keyword grep** – searches source files for issue keywords.
3. **Test discovery** – finds neighbouring ``*_test.go`` files for every
   relevant source file so the Planner knows what tests exist.
"""

from __future__ import annotations

import json
import os
import re

from agents import get_llm
from config import MAX_CONTEXT_FILES
from langchain_core.messages import HumanMessage, SystemMessage
from tools.code_search import find_test_files, read_file_in_repo, search_files
from vectorstore.pinecone_store import CodeVectorStore

_SYSTEM = """\
You are an expert Go developer. Given an issue analysis, a repository summary,
and candidate files from semantic and keyword search, choose the files most
relevant to fixing the issue. Return **only valid JSON** – no markdown fences."""


def retrieve_context(state: dict) -> dict:

    repo_path = state["repo_path"]
    repo_name = _repo_name(state["repo_url"])
    keywords = state.get("issue_keywords", [])
    components = state.get("affected_components", [])
    issue_title = state.get("issue_title", "")
    issue_body = state.get("issue_body", "")
    repo_summary = state.get("repo_summary", "")
    code_map = state.get("code_map", [])

    query = f"{issue_title} {' '.join(keywords)} {' '.join(components)}"
    store = CodeVectorStore()
    semantic_hits = store.search(query, repo_name, top_k=20)

    semantic_files: set[str] = set()
    for hit in semantic_hits:
        if hit.get("file"):
            semantic_files.add(hit["file"])

    grep_files: set[str] = set()
    for kw in keywords[:5]:  # limit to avoid flooding
        results = search_files(repo_path, kw, max_results=15)
        for r in results:
            grep_files.add(r["file"])

    for comp in components[:3]:
        results = search_files(repo_path, comp, max_results=10)
        for r in results:
            grep_files.add(r["file"])

    # ── combine candidates ──────────────────────────────────
            grep_files.add(r["file"])

    all_candidates = sorted(semantic_files | grep_files)
Keywords: {', '.join(keywords)}
Components: {', '.join(components)}
Repository summary: {repo_summary}

### Candidate files from search:
{chr(10).join(all_candidates[:40])}

### Top semantic matches:
{json.dumps(semantic_hits[:10], indent=2)}

Select the {MAX_CONTEXT_FILES} most relevant files to inspect for fixing this issue.
Return JSON:
{{
    "relevant_files": ["file1.go", "file2.go"]
}}"""

    llm = get_llm()
    resp = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])

    selected = _extract_json(resp.content)
    relevant_files = selected.get("relevant_files", all_candidates[:MAX_CONTEXT_FILES])

    file_contents: dict[str, str] = {}
    for fpath in relevant_files:
        try:
            file_contents[fpath] = read_file_in_repo(repo_path, fpath)
        except FileNotFoundError:
            continue

    all_tests = find_test_files(repo_path)
    related_tests: set[str] = set()

    for src in relevant_files:
        # Convention: foo.go → foo_test.go
        base, _ = os.path.splitext(src)
        test_candidate = base + "_test.go"
        if test_candidate in all_tests:
            related_tests.add(test_candidate)

        # Same-directory tests
        src_dir = os.path.dirname(src)
        for t in all_tests:
            if os.path.dirname(t) == src_dir:
                related_tests.add(t)

    test_contents: dict[str, str] = {}
    for tpath in sorted(related_tests)[:5]:  # cap test files
        try:
            test_contents[tpath] = read_file_in_repo(repo_path, tpath)
        except FileNotFoundError:
            continue

    return {
        "relevant_files": list(relevant_files),
        "file_contents": file_contents,
        "test_files": sorted(related_tests),
        "test_contents": test_contents,
        "messages": [
            f"✓ Retrieved {len(file_contents)} source files + "
            f"{len(test_contents)} test files"
        ],
    }


def _repo_name(url: str) -> str:
    m = re.match(r"(?:https?://github\.com/)?([^/]+/[^/]+)", url)
    name = m.group(1).rstrip("/") if m else url
    return name.removesuffix(".git")


def _extract_json(text: str) -> dict:
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {}
