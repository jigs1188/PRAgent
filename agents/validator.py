from __future__ import annotations

from tools.test_runner import run_all_checks


def validate_changes(state: dict) -> dict:

    repo_path = state["repo_path"]
    retry_count = state.get("retry_count", 0)

    print(f"  ↳ Validating (attempt {retry_count + 1}) …")
    results = run_all_checks(repo_path)

    passed = results["passed"]
    errors = results["errors"]

    # Truncate huge outputs so they fit in the next LLM prompt
    truncated_errors = [e[:2000] for e in errors]

    status = "PASSED ✓" if passed else "FAILED ✗"
    msgs = [
        f"{'✓' if passed else '✗'} Validation {status} "
        f"(build={'✓' if results['build'].passed else '✗'} "
        f"vet={'✓' if results['vet'].passed else '✗'} "
        f"test={'✓' if results['test'].passed else '✗'})"
    ]

    # Increment retry_count only on failure so that _should_retry sees the
    # correct count.  A passed validation still increments so the log is
    # accurate, but we cap at MAX_RETRIES to avoid the off-by-one where
    # the graph's conditional edge check (retry_count < MAX_RETRIES) was
    # evaluated against the *already incremented* value, causing one fewer
    # retry than expected.
    from config import MAX_RETRIES
    new_retry_count = retry_count + 1 if not passed else retry_count

    return {
        "build_output": results["build"].output,
        "test_output": results["test"].output,
        "vet_output": results["vet"].output,
        "validation_passed": passed,
        "validation_errors": truncated_errors,
        "retry_count": new_retry_count,
        "messages": msgs,
    }
