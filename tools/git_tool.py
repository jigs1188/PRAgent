"""
Git operations – clone, branch, diff, apply file changes.
"""

from __future__ import annotations

import os
import shutil

from git import Repo  # GitPython

from config import REPOS_DIR


def clone_repo(repo_url: str, dest: str | None = None) -> str:
    # Normalise URL
    if not repo_url.startswith("http"):
        repo_url = f"https://github.com/{repo_url}.git"
    elif not repo_url.endswith(".git"):
        repo_url = repo_url.rstrip("/") + ".git"

    repo_name = repo_url.split("/")[-1].replace(".git", "")
    local_path = dest or os.path.join(REPOS_DIR, repo_name)

    if os.path.isdir(local_path):
        print(f"  ↳ Repository already cloned at {local_path}")
        try:
            repo = Repo(local_path)
            has_changes = repo.is_dirty(untracked_files=True)
            if has_changes:
                print("  ↳ Stashing local changes before pull …")
                repo.git.stash("push", "--include-untracked", "-m", "ai-agent-stash")
            origin = repo.remotes.origin
            origin.pull()
            print("  ↳ Pulled latest changes")
            if has_changes:
                try:
                    repo.git.stash("drop")
                except Exception:
                    pass
        except Exception as exc:
            print(f"  ↳ Could not pull: {exc}")
        return os.path.abspath(local_path)

    os.makedirs(REPOS_DIR, exist_ok=True)
    print(f"  ↳ Cloning {repo_url} → {local_path} …")
    Repo.clone_from(repo_url, local_path, depth=1)
    return os.path.abspath(local_path)


def create_branch(repo_path: str, branch_name: str) -> str:
    """Create and checkout a new branch.  Returns the branch name.

    If the branch already exists (from a previous run), it is reset to the
    current HEAD of the default branch so each run starts from a clean state.
    """
    repo = Repo(repo_path)
    if branch_name in [b.name for b in repo.branches]:
        repo.git.checkout(branch_name)
        try:
            # Figure out the default branch (main or master)
            default = repo.git.symbolic_ref("refs/remotes/origin/HEAD", "--short")
            default = default.split("/")[-1]  # e.g. "origin/main" → "main"
        except Exception:
            default = "main"
        try:
            repo.git.reset("--hard", f"origin/{default}")
            print(f"  ↳ Reset branch {branch_name} to origin/{default}")
        except Exception:
            repo.git.reset("--hard", "HEAD")
    else:
        repo.git.checkout("-b", branch_name)
    print(f"  ↳ On branch {branch_name}")
    return branch_name


def get_diff(repo_path: str) -> str:
    """Return the unified diff of all unstaged + staged changes."""
    repo = Repo(repo_path)
    repo.git.add(A=True)
    diff = repo.git.diff("--cached")
    return diff


def apply_file_content(repo_path: str, relative_path: str, content: str) -> None:
    """Write *content* to *relative_path* inside the repo.

    Creates any necessary parent directories.  Handles the case where
    ``relative_path`` has no directory component (e.g. a top-level file).
    """
    full_path = os.path.join(repo_path, relative_path)
    dir_name = os.path.dirname(full_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(full_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def get_latest_commit_hash(repo_path: str) -> str:
    """Return the HEAD commit short hash (used for caching)."""
    repo = Repo(repo_path)
    return repo.head.commit.hexsha[:12]
