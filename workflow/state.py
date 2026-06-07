"""
Shared state schema for the LangGraph workflow.

Every agent node receives the full state and returns a *partial* dict
with only the keys it wants to update.  LangGraph merges the update
into the running state automatically.

The ``messages`` field uses ``operator.add`` so log entries from each
node are appended rather than replaced.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict, total=False):

    # ── Input (set once by main.py) ─────────────────────────
    repo_url: str                       # e.g. "spf13/cobra"
    issue_url: str                      # full GitHub issue URL
    issue_number: int

    # ── Issue analysis ──────────────────────────────────────
    issue_title: str
    issue_body: str
    issue_comments: list[str]           # first N comments
    issue_type: str                     # bug | enhancement | docs | test | refactor
    issue_keywords: list[str]
    affected_components: list[str]

    # ── Repository ──────────────────────────────────────────
    repo_path: str                      # local clone path
    repo_structure: str                 # directory tree string
    repo_summary: str                   # LLM-generated summary
    code_map: list[dict]                # [{name, type, file, line, signature}, …]

    # ── Context retrieval ───────────────────────────────────
    relevant_files: list[str]
    file_contents: dict[str, str]       # path → source
    test_files: list[str]               # discovered *_test.go paths
    test_contents: dict[str, str]       # path → test source

    # ── Planning ────────────────────────────────────────────
    plan: str

    # ── Code changes (search/replace patches) ──────────────
    patches: list[dict]                 # [{file, search, replace}, …]

    # ── Validation ──────────────────────────────────────────
    build_output: str
    test_output: str
    vet_output: str
    validation_passed: bool
    validation_errors: list[str]
    retry_count: int

    # ── Final output ────────────────────────────────────────
    pr_title: str
    pr_body: str
    diff: str
    branch_name: str

    # ── Logs (accumulates via operator.add) ─────────────────
    messages: Annotated[list[str], operator.add]
