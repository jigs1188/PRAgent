"""
Planner Agent

Receives the issue analysis and retrieved context, then produces a
step-by-step plan for how to fix the issue — which files to modify,
what changes to make, and which tests to add or update.
"""

from __future__ import annotations

from agents import get_llm
from langchain_core.messages import HumanMessage, SystemMessage

_SYSTEM = """\
You are a senior Go engineer planning a fix for a GitHub issue.

Rules:
- Produce a clear, numbered, step-by-step plan.
- Specify EXACT file paths for every change.
- If existing tests need updating, say which test functions.
- If new tests are needed, describe what they should cover.
- Keep the change minimal – do NOT refactor unrelated code.
- Follow the project's existing code style and conventions."""


def plan_changes(state: dict) -> dict:

    issue_title = state.get("issue_title", "")
    issue_body = state.get("issue_body", "")
    issue_type = state.get("issue_type", "bug")
    issue_comments = state.get("issue_comments", [])
    repo_summary = state.get("repo_summary", "")
    relevant_files = state.get("relevant_files", [])
    file_contents = state.get("file_contents", {})
    test_files = state.get("test_files", [])
    test_contents = state.get("test_contents", {})

    source_section = _format_files(file_contents, max_lines=200)
    test_section = _format_files(test_contents, max_lines=100)

    prompt = f"""## Issue
**{issue_title}** (type: {issue_type})

{issue_body}

### Comments
{chr(10).join(issue_comments[:5]) if issue_comments else 'None'}

## Repository Summary
{repo_summary}

## Relevant Source Files
{source_section}

## Existing Test Files
{test_section if test_section else 'No related test files found.'}

## Test File Paths
{chr(10).join(test_files) if test_files else 'None discovered'}

---

Produce a numbered plan to fix this issue.  For each step include:
- The exact file path
- What to change (describe the code modification)
- Why the change is needed
"""

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])

    plan = response.content

    return {
        "plan": plan,
        "messages": [f"✓ Plan generated ({len(plan)} chars)"],
    }


def _format_files(mapping: dict[str, str], max_lines: int = 200) -> str:
    """Format a ``{path: content}`` dict into a prompt-friendly block."""
    parts: list[str] = []
    for fpath, content in mapping.items():
        lines = content.splitlines()
        if len(lines) > max_lines:
            truncated = "\n".join(lines[:max_lines])
            truncated += f"\n... ({len(lines) - max_lines} more lines)"
        else:
            truncated = content
        parts.append(f"### {fpath}\n```go\n{truncated}\n```")
    return "\n\n".join(parts)
