from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.context_retriever import retrieve_context
from agents.issue_analyzer import analyze_issue
from agents.patch_generator import generate_patches
from agents.planner import plan_changes
from agents.pr_generator import generate_pr
from agents.repo_mapper import map_repository
from agents.validator import validate_changes
from config import MAX_RETRIES
from workflow.state import AgentState


def _should_retry(state: dict) -> str:
    if state.get("validation_passed", False):
        return "generate_pr"
    if state.get("retry_count", 0) < MAX_RETRIES:
        return "generate_patches"
    # Max retries exhausted – generate PR anyway (best-effort)
    return "generate_pr"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("analyze_issue", analyze_issue)
    graph.add_node("map_repository", map_repository)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("plan_changes", plan_changes)
    graph.add_node("generate_patches", generate_patches)
    graph.add_node("validate_changes", validate_changes)
    graph.add_node("generate_pr", generate_pr)

    graph.set_entry_point("analyze_issue")
    graph.add_edge("analyze_issue", "map_repository")
    graph.add_edge("map_repository", "retrieve_context")
    graph.add_edge("retrieve_context", "plan_changes")
    graph.add_edge("plan_changes", "generate_patches")
    graph.add_edge("generate_patches", "validate_changes")

    graph.add_conditional_edges(
        "validate_changes",
        _should_retry,
        {
            "generate_patches": "generate_patches",
            "generate_pr": "generate_pr",
        },
    )

    graph.add_edge("generate_pr", END)

    return graph.compile()
