"""
PR Generator Agent

Produces a professional pull-request title and body based on the
issue, plan, and unified diff of all changes.
"""

from __future__ import annotations

from agents import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
from tools.git_tool import get_diff

_SYSTEM = """\
You are a senior open-source contributor writing a pull request.

Rules:
- Title: concise imperative sentence (≤72 chars).
- Body must include these sections:
  ## Problem
  ## Solution
  ## Changes
  ## Tests
- Reference the original issue number with "Fixes #N" or "Closes #N".
- Be specific about what changed and why.
- Do NOT include markdown code fences around the entire response."""


def generate_pr(state: dict) -> dict:
    """LangGraph node: create PR title + body from the diff."""

    repo_path = state["repo_path"]
    issue_number = state.get("issue_number", 0)
    issue_title = state.get("issue_title", "")
    issue_body = state.get("issue_body", "")
    plan = state.get("plan", "")
    validation_passed = state.get("validation_passed", False)

    diff = get_diff(repo_path)

    if not diff:
        return {
            "pr_title": "",
            "pr_body": "No changes were made.",
            "diff": "",
            "messages": ["⚠ No diff generated – no files were changed."],
        }

    prompt = f"""## Original Issue #{issue_number}: {issue_title}

{issue_body[:1500]}

## Plan
{plan[:1500]}

## Diff
```diff
{diff[:6000]}
```

## Validation Status
{'All checks passed ✓' if validation_passed else 'Some checks failed ✗ (best-effort submission)'}

Write the PR title and body now.
Format your response exactly as:

TITLE: <title here>

BODY:
<body here>
"""

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])

    pr_title, pr_body = _parse_pr(response.content, issue_number)

    return {
        "pr_title": pr_title,
        "pr_body": pr_body,
        "diff": diff,
        "messages": [f"✓ PR generated: {pr_title}"],
    }


def _parse_pr(text: str, issue_number: int) -> tuple[str, str]:
    """Extract title and body from the LLM response."""
    title = ""
    body = text

    # Try TITLE: / BODY: format
    if "TITLE:" in text:
        parts = text.split("TITLE:", 1)
        remainder = parts[1]
        if "BODY:" in remainder:
            title_part, body_part = remainder.split("BODY:", 1)
            title = title_part.strip()
            body = body_part.strip()
        else:
            lines = remainder.strip().splitlines()
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip()

    if not title:
        # Fallback: first line is title
        lines = text.strip().splitlines()
        title = lines[0].strip().lstrip("#").strip()
        body = "\n".join(lines[1:]).strip()

    # Ensure issue reference exists
    ref = f"Fixes #{issue_number}"
    if f"#{issue_number}" not in body:
        body = f"{ref}\n\n{body}"

    return title, body
