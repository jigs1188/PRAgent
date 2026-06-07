"""
Patch Generator Agent

Generates **search/replace patches** (not full-file rewrites) following
the plan.  Each patch is a targeted edit:

    <<<<<<< SEARCH
    original code to find
    =======
    replacement code
    >>>>>>> REPLACE

The patches are then applied to the local checkout.
"""

from __future__ import annotations

import os
import re

from agents import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
from tools.git_tool import apply_file_content

_SYSTEM = """\
You are an expert Go developer applying a fix plan.

Rules:
- Output ONLY search/replace blocks – no commentary before or after.
- Use this EXACT format for every change:

### File: path/to/file.go

<<<<<<< SEARCH
exact original code
=======
replacement code
>>>>>>> REPLACE

- The SEARCH block must contain the EXACT text from the original file
  (whitespace-sensitive).  Copy it character-for-character.
- Make MINIMAL changes – do not reformat, rename, or refactor code
  outside the scope of the fix.
- If you need to add a new file, use an empty SEARCH block.
- If you need to add a new test, include it as a patch to the *_test.go file.
- Do NOT wrap your output in markdown code fences."""

_RETRY_ADDENDUM = """

## Previous Attempt Failed

The following errors occurred when validating your last set of patches.
Fix them while keeping the same overall approach.

### Errors
{errors}

### Previous Patches Applied
{prev_patches}
"""


def generate_patches(state: dict) -> dict:

    plan = state.get("plan", "")
    file_contents = state.get("file_contents", {})
    test_contents = state.get("test_contents", {})
    repo_path = state["repo_path"]
    issue_title = state.get("issue_title", "")

    retry_count = state.get("retry_count", 0)
    validation_errors = state.get("validation_errors", [])
    prev_patches = state.get("patches", [])

    all_files = {**file_contents, **test_contents}
    source_block = _format_sources(all_files)

    prompt = f"""## Issue
{issue_title}

## Plan
{plan}

## Source Files
{source_block}

Generate search/replace patches to implement the plan above.
"""

    if retry_count > 0 and validation_errors:
        prompt += _RETRY_ADDENDUM.format(
            errors="\n".join(validation_errors),
            prev_patches=_format_prev_patches(prev_patches),
        )

    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])

    raw_patches = _parse_patches(response.content)
    apply_errors: list[str] = []

    for patch in raw_patches:
        fpath = patch["file"]
        search = patch["search"]
        replace = patch["replace"]

        abs_path = os.path.join(repo_path, fpath)

        if search == "":
            # New file or append
            apply_file_content(repo_path, fpath, replace)
            applied.append(patch)
            continue

        try:
            with open(abs_path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except FileNotFoundError:
            apply_errors.append(f"File not found: {fpath}")
            continue

        if search not in content:
            # Try with normalised whitespace
            normalised_search = _normalise_ws(search)
            normalised_content = _normalise_ws(content)
            if normalised_search in normalised_content:
                # Find and replace with original spacing
                content = _fuzzy_replace(content, search, replace)
            else:
                apply_errors.append(
                    f"SEARCH block not found in {fpath}:\n{search[:200]}"
                )
                continue
        else:
            content = content.replace(search, replace, 1)

        apply_file_content(repo_path, fpath, content)
        applied.append(patch)

    msgs = [f"✓ Applied {len(applied)}/{len(raw_patches)} patches"]
    if apply_errors:
        msgs.append(f"⚠ {len(apply_errors)} patches failed to apply")

    return {
        "patches": applied,
        "validation_errors": apply_errors if apply_errors else [],
        "messages": msgs,
    }


_PATCH_RE = re.compile(
    r"###\s*File:\s*(?P<file>\S+)[^\r\n]*\r?\n"
    r"<<<<<<< SEARCH\r?\n"
    r"(?P<search>.*?)"
    r"=======\r?\n"
    r"(?P<replace>.*?)"
    r">>>>>>> REPLACE",
    re.DOTALL,
)


def _parse_patches(text: str) -> list[dict]:
    """Extract all search/replace patches from LLM output."""
    patches: list[dict] = []
    for m in _PATCH_RE.finditer(text):
        patches.append(
            {
                "file": m.group("file").strip(),
                "search": m.group("search"),
                "replace": m.group("replace"),
            }
        )
    return patches


def _normalise_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _fuzzy_replace(content: str, search: str, replace: str) -> str:
    """Attempt a line-by-line fuzzy match when exact match fails."""
    search_lines = search.strip().splitlines()
    content_lines = content.splitlines()

    for i in range(len(content_lines) - len(search_lines) + 1):
        window = content_lines[i : i + len(search_lines)]
        if all(
            sl.strip() == cl.strip()
            for sl, cl in zip(search_lines, window)
        ):
            # Found a whitespace-fuzzy match — replace
            replace_lines = replace.strip().splitlines()
            new_lines = content_lines[:i] + replace_lines + content_lines[i + len(search_lines) :]
            return "\n".join(new_lines) + "\n"

    # Fallback: return content unchanged
    return content


def _format_sources(mapping: dict[str, str]) -> str:
    parts: list[str] = []
    for fpath, content in mapping.items():
        lines = content.splitlines()
        if len(lines) > 300:
            content = "\n".join(lines[:300]) + f"\n... ({len(lines) - 300} more lines)"
        parts.append(f"### {fpath}\n```go\n{content}\n```")
    return "\n\n".join(parts)


def _format_prev_patches(patches: list[dict]) -> str:
    parts: list[str] = []
    for p in patches:
        parts.append(
            f"### File: {p['file']}\n"
            f"<<<<<<< SEARCH\n{p['search']}=======\n{p['replace']}>>>>>>> REPLACE"
        )
    return "\n\n".join(parts)
