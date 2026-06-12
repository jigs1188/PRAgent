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

    issue = fetch_issue(repo_url, issue_number=issue_number, issue_url=issue_url)
    repo_name = issue["repo_name"]
    issue_number = issue["issue_number"]
    issue_title = issue["title"]
    issue_body = issue["body"]
    labels = issue["labels"]
    issue_comments = issue["comments"]

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


def fetch_issue(repo_url: str, issue_number: int | None = None, issue_url: str = "") -> dict:
    repo_name = _repo_name(repo_url)
    issue_number = issue_number or _issue_number(issue_url)
    if not issue_number:
        raise RuntimeError("Issue number is required. Pass --issue 123 or a full GitHub issue URL.")

    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    api = f"https://api.github.com/repos/{repo_name}/issues/{issue_number}"
    try:
        resp = requests.get(api, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise RuntimeError("GitHub API returned 401 Unauthorized. Check GITHUB_TOKEN in .env.")
        if resp.status_code == 403:
            raise RuntimeError(
                "GitHub API returned 403 Forbidden, likely rate-limited. "
                "Set GITHUB_TOKEN in .env to raise the limit."
            )
        if resp.status_code == 404:
            raise RuntimeError(f"Issue #{issue_number} not found in {repo_name}.")
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch GitHub issue: {exc}") from exc

    data = resp.json()
    comments = _fetch_comments(api, headers)
    return {
        "repo_name": repo_name,
        "issue_number": issue_number,
        "title": data.get("title", ""),
        "body": data.get("body", "") or "",
        "labels": [lb["name"] for lb in data.get("labels", [])],
        "comments": comments,
    }


def _repo_name(url: str) -> str:
    match = re.match(r"(?:https?://github\.com/)?([^/]+/[^/]+)", url)
    repo_name = match.group(1).rstrip("/") if match else url
    return repo_name.removesuffix(".git")


def _issue_number(issue_url: str) -> int | None:
    match = re.search(r"/issues/(\d+)", issue_url)
    return int(match.group(1)) if match else None


def _fetch_comments(api: str, headers: dict[str, str]) -> list[str]:
    try:
        resp = requests.get(f"{api}/comments", headers=headers, timeout=30)
        resp.raise_for_status()
        raw_comments = resp.json()
    except requests.RequestException:
        raw_comments = []

    comments: list[str] = []
    for item in raw_comments[:15]:
        user = item.get("user", {}).get("login", "unknown")
        body = item.get("body", "")
        comments.append(f"@{user}: {body}")
    return comments
