#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import warnings

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress annoying Langchain Gemini warning
warnings.filterwarnings("ignore", message="Both GOOGLE_API_KEY and GEMINI_API_KEY are set")


def main() -> None:
    # Force UTF-8 on Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Agentic AI Contributor for Open-Source Go Projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository (e.g. spf13/cobra)",
    )
    parser.add_argument(
        "--issue",
        required=True,
        help="Issue number or full URL",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override MODEL_NAME from config (e.g. gemini-1.5-pro)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Override LLM_PROVIDER from config (gemini|openai|anthropic)",
    )
    args = parser.parse_args()

    if args.model:
        import config
        config.MODEL_NAME = args.model
        print(f"⚙  Model overridden → {args.model}")

    if args.provider:
        import config
        config.LLM_PROVIDER = args.provider
        print(f"⚙  Provider overridden → {args.provider}")

    issue_input = args.issue
    issue_number = None
    issue_url = ""

    if issue_input.startswith("http"):
        issue_url = issue_input
        m = re.search(r"/issues/(\d+)", issue_input)
        if m:
            issue_number = int(m.group(1))
    else:
        try:
            issue_number = int(issue_input)
        except ValueError:
            print(f"ERROR: Cannot parse issue number from '{issue_input}'")
            sys.exit(1)

    if issue_number is None:
        print("ERROR: Could not resolve issue number.")
        sys.exit(1)

    if not issue_url:
        repo_clean = args.repo.rstrip("/")
        issue_url = f"https://github.com/{repo_clean}/issues/{issue_number}"

    print("=" * 60)
    print("  Agentic Go Contributor")
    print("=" * 60)
    print(f"  Repository : {args.repo}")
    print(f"  Issue      : #{issue_number}")
    print(f"  URL        : {issue_url}")

    import config
    print(f"  LLM        : {config.LLM_PROVIDER} / {config.MODEL_NAME}")
    print("=" * 60)
    print()

    from workflow.graph import build_graph

    graph = build_graph()

    initial_state = {
        "repo_url": args.repo,
        "issue_url": issue_url,
        "issue_number": issue_number,
        "messages": [],
        "retry_count": 0,
    }

    start = time.time()

    print("▶ Starting agent workflow …\n")

    final_state = None
    try:
        for step in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in step.items():
                # Print log messages from this node
                for msg in node_output.get("messages", []):
                    print(f"  [{node_name}] {msg}")
                final_state = {**(final_state or initial_state), **node_output}
            print()
    except KeyboardInterrupt:
        print("\n\n⚠  Interrupted by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n\n❌ Workflow failed: {exc}")
        print(
            "\nTips:\n"
            "  • Ensure GOOGLE_API_KEY (or OPENAI_API_KEY) is set in .env\n"
            "  • Ensure PINECONE_API_KEY is set in .env\n"
            "  • Ensure GITHUB_TOKEN is set to avoid API rate limits\n"
            "  • Ensure Go is installed and on PATH (required for validation)\n"
        )
        import traceback
        traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start
    print(f"⏱  Total time: {elapsed:.1f}s\n")

    if final_state is None:
        print("ERROR: Workflow produced no output.")
        sys.exit(1)

    pr_title = final_state.get("pr_title", "")
    pr_body = final_state.get("pr_body", "")
    diff = final_state.get("diff", "")
    branch = final_state.get("branch_name", "")
    passed = final_state.get("validation_passed", False)

    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"  Branch    : {branch}")
    print(f"  Validated : {'✓ PASSED' if passed else '✗ FAILED (best-effort)'}")
    print()
    print(f"  PR Title  : {pr_title}")
    print("-" * 60)
    print(pr_body)
    print("-" * 60)

    out_dir = os.path.join(config.OUTPUT_DIR, f"issue-{issue_number}")
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "pr_title.txt"), "w") as f:
        f.write(pr_title)

    with open(os.path.join(out_dir, "pr_body.md"), "w") as f:
        f.write(pr_body)

    with open(os.path.join(out_dir, "changes.diff"), "w") as f:
        f.write(diff)

    with open(os.path.join(out_dir, "plan.md"), "w") as f:
        f.write(final_state.get("plan", ""))

    with open(os.path.join(out_dir, "agent_log.json"), "w") as f:
        log_data = {
            "repo": args.repo,
            "issue_number": issue_number,
            "issue_title": final_state.get("issue_title", ""),
            "issue_type": final_state.get("issue_type", ""),
            "relevant_files": final_state.get("relevant_files", []),
            "test_files": final_state.get("test_files", []),
            "validation_passed": passed,
            "retry_count": final_state.get("retry_count", 0),
            "branch_name": branch,
            "pr_title": pr_title,
            "elapsed_seconds": round(elapsed, 1),
            "messages": final_state.get("messages", []),
        }
        json.dump(log_data, f, indent=2)

    print(f"\n📁 Output saved to: {out_dir}/")
    print("   ├── pr_title.txt")
    print("   ├── pr_body.md")
    print("   ├── changes.diff")
    print("   ├── plan.md")
    print("   └── agent_log.json")


if __name__ == "__main__":
    main()
