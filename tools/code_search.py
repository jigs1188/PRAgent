from __future__ import annotations

import fnmatch
import os
import re
from typing import Generator

# File extensions to include when scanning a Go repository
_GO_EXTENSIONS = {".go", ".mod", ".sum", ".md", ".txt", ".yaml", ".yml", ".toml"}

# Directories to always skip
_SKIP_DIRS = {".git", "vendor", "node_modules", "__pycache__", ".idea", ".vscode"}


# ─────────────────────────── directory tree ─────────────────
def get_repo_structure(repo_path: str, max_depth: int = 4) -> str:
    lines: list[str] = []
    repo_path = os.path.abspath(repo_path)

    for root, dirs, files in os.walk(repo_path):
        # Skip hidden / vendor dirs
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))

        depth = root.replace(repo_path, "").count(os.sep)
        if depth > max_depth:
            dirs.clear()
            continue

        indent = "  " * depth
        basename = os.path.basename(root)
        lines.append(f"{indent}{basename}/")

        sub_indent = "  " * (depth + 1)
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1]
            if ext in _GO_EXTENSIONS or fname in {"Makefile", "Dockerfile", "go.mod", "go.sum"}:
                lines.append(f"{sub_indent}{fname}")

    return "\n".join(lines)


def search_files(
    repo_path: str,
    pattern: str,
    *,
    file_glob: str = "*.go",
    max_results: int = 50,
) -> list[dict]:
    results: list[dict] = []
    regex = re.compile(pattern, re.IGNORECASE)

    for fpath in _iter_files(repo_path, file_glob):
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    if regex.search(line):
                        results.append(
                            {
                                "file": os.path.relpath(fpath, repo_path),
                                "line": lineno,
                                "match": line.rstrip(),
                            }
                        )
                        if len(results) >= max_results:
                            return results
        except (OSError, UnicodeDecodeError):
            continue

    return results


def read_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def read_file_in_repo(repo_path: str, relative_path: str) -> str:
    return read_file(os.path.join(repo_path, relative_path))


def find_files(
    repo_path: str,
    pattern: str = "*.go",
) -> list[str]:
    return list(_iter_files_relative(repo_path, pattern))


def find_test_files(repo_path: str) -> list[str]:
    return find_files(repo_path, "*_test.go")


def _iter_files(repo_path: str, glob_pattern: str) -> Generator[str, None, None]:
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            if fnmatch.fnmatch(fname, glob_pattern):
                yield os.path.join(root, fname)


def _iter_files_relative(repo_path: str, glob_pattern: str) -> Generator[str, None, None]:
    for fpath in _iter_files(repo_path, glob_pattern):
        yield os.path.relpath(fpath, repo_path)
