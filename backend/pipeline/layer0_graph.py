"""Layer 0 — knowledge-graph lookup: full relationship context queried at the
start of every dispute and passed through all subsequent layers."""
from backend.graph.graph import get_graph


def run(ctx) -> dict:
    return get_graph().get_dispute_context(ctx.dispute["id"])
