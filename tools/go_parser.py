"""
Go source parser – extract functions, methods, structs, interfaces.

Uses tree-sitter for accurate AST parsing with a regex fallback
so the system works even if tree-sitter is not installed.
"""

from __future__ import annotations

import os
import re
from typing import Generator

from tools.code_search import find_files

# ──────────────────────── tree-sitter setup ──────────────────
try:
    import tree_sitter_go as _tsgo                     # type: ignore[import-untyped]
    from tree_sitter import Language, Parser            # type: ignore[import-untyped]

    _GO_LANG = Language(_tsgo.language())
    _parser = Parser(_GO_LANG)
    _HAS_TREE_SITTER = True
except Exception:
    _HAS_TREE_SITTER = False


# ━━━━━━━━━━━━━━━━━━━━━━ public API ━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_go_file(filepath: str) -> list[dict]:
    """Parse a single Go file and return code-map entries.

    Each entry is a dict::

        {
            "name":      "Execute",
            "type":      "function" | "method" | "struct" | "interface",
            "file":      "command.go",
            "line":      42,
            "end_line":  78,
            "signature": "func (c *Command) Execute() error",
        }
    """
    if _HAS_TREE_SITTER:
        return _parse_tree_sitter(filepath)
    return _parse_regex(filepath)


def build_code_map(repo_path: str) -> list[dict]:
    """Build a full code map of the repository (all ``.go`` files)."""
    code_map: list[dict] = []
    for rel_path in find_files(repo_path, "*.go"):
        abs_path = os.path.join(repo_path, rel_path)
        entries = parse_go_file(abs_path)
        for entry in entries:
            entry["file"] = rel_path          # normalise to relative
        code_map.extend(entries)
    return code_map


# ━━━━━━━━━━━━━━━━━━━━━━ tree-sitter impl ━━━━━━━━━━━━━━━━━━━

def _parse_tree_sitter(filepath: str) -> list[dict]:
    with open(filepath, "rb") as fh:
        source = fh.read()

    tree = _parser.parse(source)
    entries: list[dict] = []

    for node in _walk(tree.root_node):
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                entries.append(
                    _entry(
                        name=name_node.text.decode(),
                        kind="function",
                        filepath=filepath,
                        node=node,
                        source=source,
                    )
                )

        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                entries.append(
                    _entry(
                        name=name_node.text.decode(),
                        kind="method",
                        filepath=filepath,
                        node=node,
                        source=source,
                    )
                )

        elif node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    tn = child.child_by_field_name("name")
                    tt = child.child_by_field_name("type")
                    if tn and tt:
                        kind = {
                            "struct_type": "struct",
                            "interface_type": "interface",
                        }.get(tt.type, "type_alias")
                        entries.append(
                            _entry(
                                name=tn.text.decode(),
                                kind=kind,
                                filepath=filepath,
                                node=node,
                                source=source,
                            )
                        )

    return entries


def _entry(*, name: str, kind: str, filepath: str, node, source: bytes) -> dict:
    """Build a code-map dict from a tree-sitter node."""
    # Signature = text from node start to the opening brace (or end of node)
    sig_bytes = source[node.start_byte: node.end_byte]
    sig_text = sig_bytes.decode(errors="replace")
    brace = sig_text.find("{")
    signature = sig_text[: brace].strip() if brace != -1 else sig_text.split("\n")[0].strip()

    return {
        "name": name,
        "type": kind,
        "file": filepath,
        "line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "signature": signature,
    }


def _walk(node) -> Generator:
    yield node
    for child in node.children:
        yield from _walk(child)


# ━━━━━━━━━━━━━━━━━━━━━━ regex fallback ━━━━━━━━━━━━━━━━━━━━━

# Patterns that capture the most common Go declarations
_RE_FUNC = re.compile(
    r"^func\s+(?P<sig>(?P<name>\w+)\s*\(.*)"
    , re.MULTILINE,
)
_RE_METHOD = re.compile(
    r"^func\s+\((?P<recv>[^)]+)\)\s+(?P<sig>(?P<name>\w+)\s*\(.*)"
    , re.MULTILINE,
)
_RE_STRUCT = re.compile(
    r"^type\s+(?P<name>\w+)\s+struct\s*\{", re.MULTILINE
)
_RE_INTERFACE = re.compile(
    r"^type\s+(?P<name>\w+)\s+interface\s*\{", re.MULTILINE
)


def _parse_regex(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    source = "".join(lines)

    entries: list[dict] = []

    for m in _RE_METHOD.finditer(source):
        lineno = source[: m.start()].count("\n") + 1
        sig = f"func ({m.group('recv')}) {m.group('sig').split('{')[0].strip()}"
        entries.append({
            "name": m.group("name"),
            "type": "method",
            "file": filepath,
            "line": lineno,
            "end_line": lineno,
            "signature": sig,
        })

    for m in _RE_FUNC.finditer(source):
        # Skip if it's actually a method (already captured)
        pre = source[max(0, m.start() - 1): m.start()]
        if pre.endswith(")"):
            continue
        lineno = source[: m.start()].count("\n") + 1
        sig = f"func {m.group('sig').split('{')[0].strip()}"
        entries.append({
            "name": m.group("name"),
            "type": "function",
            "file": filepath,
            "line": lineno,
            "end_line": lineno,
            "signature": sig,
        })

    for m in _RE_STRUCT.finditer(source):
        lineno = source[: m.start()].count("\n") + 1
        entries.append({
            "name": m.group("name"),
            "type": "struct",
            "file": filepath,
            "line": lineno,
            "end_line": lineno,
            "signature": f"type {m.group('name')} struct",
        })

    for m in _RE_INTERFACE.finditer(source):
        lineno = source[: m.start()].count("\n") + 1
        entries.append({
            "name": m.group("name"),
            "type": "interface",
            "file": filepath,
            "line": lineno,
            "end_line": lineno,
            "signature": f"type {m.group('name')} interface",
        })

    return entries
