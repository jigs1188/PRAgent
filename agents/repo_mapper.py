from __future__ import annotations

import os
import re

from agents import get_llm
from config import REPOS_DIR
from langchain_core.messages import HumanMessage, SystemMessage
from tools.code_search import get_repo_structure, read_file_in_repo
from tools.git_tool import clone_repo, create_branch, get_latest_commit_hash
from tools.go_parser import build_code_map
from vectorstore.local_store import LocalVectorStore


def map_repository(state: dict) -> dict:

    repo_url = state["repo_url"]
    issue_number = state.get("issue_number", 0)

    match = re.match(r"(?:https?://github\.com/)?([^/]+/[^/]+)", repo_url)
    repo_name = match.group(1).rstrip("/") if match else repo_url
    repo_name = repo_name.removesuffix(".git")

    repo_path = clone_repo(repo_name)

    branch_name = f"ai/fix-issue-{issue_number}"
    create_branch(repo_path, branch_name)

    # ── build code map (tree-sitter or regex) ───────────────
    commit_hash = get_latest_commit_hash(repo_path)

    store = LocalVectorStore()
    if store.is_cached(repo_name, commit_hash):
        print("  ↳ Code map already indexed (cache hit)")
        # Still need to build the in-memory code_map for later agents
        code_map = build_code_map(repo_path)
    else:
        print("  ↳ Building code map …")
        code_map = build_code_map(repo_path)
        try:
            count = store.index_code_map(code_map, repo_name)
            store.save_cache(repo_name, commit_hash, count)
        except Exception as exc:
            print(f"  ⚠  Embedding/Indexing failed: {exc}. Proceeding with grep/keyword fallback.")
            store.save_cache(repo_name, commit_hash, 0)

    repo_structure = get_repo_structure(repo_path)

    readme = _safe_read(repo_path, "README.md")
    gomod = _safe_read(repo_path, "go.mod")

    llm = get_llm()
    summary_resp = llm.invoke([
        SystemMessage(
            content="You are a Go expert. Summarise this repository in 3-5 sentences: "
                    "purpose, main packages, entry points, testing conventions."
        ),
        HumanMessage(
            content=f"## README (truncated)\n{readme[:3000]}\n\n"
                    f"## go.mod\n{gomod[:1000]}\n\n"
                    f"## Directory tree\n{repo_structure[:2000]}"
        ),
    ])

    return {
        "repo_path": repo_path,
        "repo_structure": repo_structure,
        "repo_summary": summary_resp.content,
        "code_map": code_map,
        "branch_name": branch_name,
        "messages": [
            f"✓ Repository mapped – {len(code_map)} symbols indexed, "
            f"branch '{branch_name}' created"
        ],
    }


def _safe_read(repo_path: str, rel: str) -> str:
    try:
        return read_file_in_repo(repo_path, rel)
    except FileNotFoundError:
        return "(not found)"
