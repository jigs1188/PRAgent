"""
Issue Analyzer Agent

Fetches the GitHub issue **and its comments**, then uses the LLM to
classify the issue type, extract keywords, and identify affected components.
"""

from __future__ import annotations

import json
import re

import requests

from agents import get_llm
from config import GITHUB_TOKEN
from langchain_core.messages import HumanMessage, SystemMessage

_SYSTEM = """\
You are an expert Go developer analyzing a GitHub issue.
Your job is to classify the issue, extract search keywords, and identify
which parts of the codebase are likely affected.
Always respond with **valid JSON only** – no markdown fences, no commentary."""


def analyze_issue(state: dict) -> dict:

    repo_url = state["repo_url"]
    issue_number = state.get("issue_number")
    issue_url = state.get("issue_url", "")

    match = re.match(r"(?:https?://github\.com/)?([^/]+/[^/]+)", repo_url)
    repo_name = match.group(1).rstrip("/") if match else repo_url
    repo_name = repo_name.removesuffix(".git")

    if issue_url and not issue_number:
        m = re.search(r"/issues/(\d+)", issue_url)
        if m:
            issue_number = int(m.group(1))

    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    api = f"https://api.github.com/repos/{repo_name}/issues/{issue_number}"
    try:
        resp = requests.get(api, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise RuntimeError(
                "GitHub API returned 401 Unauthorized. "
                "Check your GITHUB_TOKEN in .env."
            )
        if resp.status_code == 403:
            raise RuntimeError(
                "GitHub API returned 403 Forbidden (likely rate-limited). "
                "Set GITHUB_TOKEN in .env to raise the rate limit."
            )
        if resp.status_code == 404:
            raise RuntimeError(
                f"Issue #{issue_number} not found in {repo_name}. "
                "Verify the repository name and issue number."
            )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch GitHub issue: {exc}") from exc

    data = resp.json()

    issue_title = data.get("title", "")
    issue_body = data.get("body", "") or ""
    labels = [lb["name"] for lb in data.get("labels", [])]

    comments_url = f"{api}/comments"
    try:
        cresp = requests.get(comments_url, headers=headers, timeout=30)
        raw_comments = cresp.json() if cresp.status_code == 200 else []
    except requests.RequestException:
        raw_comments = []

    issue_comments: list[str] = []
    for c in raw_comments[:15]:
        user = c.get("user", {}).get("login", "unknown")
        body = c.get("body", "")
        issue_comments.append(f"@{user}: {body}")

    prompt = f"""Analyze this GitHub issue from the **{repo_name}** repository.

## Issue #{issue_number}: {issue_title}

{issue_body}

## Labels
{', '.join(labels) if labels else 'None'}

## Comments
{chr(10).join(issue_comments) if issue_comments else 'No comments'}

Return JSON:
{{
    "issue_type": "bug | enhancement | documentation | test | refactor",
    "keywords": ["keyword1", "keyword2"],
    "affected_components": ["component_or_package_name"],
    "expected_behavior": "what should happen",
    "current_behavior": "what currently happens",
    "suggested_fix_hint": "high-level direction if obvious"
}}"""

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])

    analysis = _extract_json(response.content)

    return {
        "issue_title": issue_title,
        "issue_body": issue_body,
        "issue_comments": issue_comments,
        "issue_type": analysis.get("issue_type", "bug"),
        "issue_keywords": analysis.get("keywords", []),
        "affected_components": analysis.get("affected_components", []),
        "messages": [
            f"✓ Issue #{issue_number} analysed: {issue_title} "
            f"(type={analysis.get('issue_type', '?')})"
        ],
    }


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from LLM output."""
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
