"""Dispute lifecycle state machine (TDD §14).

filed -> evidence_gathering -> merchant_response_window -> decision ->
resolved | appealed -> (representment re-enters decision) -> final
The merchant response window is decisive: expiry resolves as
'no proof provided' and auto-favours the card member (Layer 7 override).
"""

STATES = ["filed", "evidence_gathering", "merchant_response_window",
          "decision", "escalated", "resolved", "appealed", "final"]

TRANSITIONS = {
    "filed": {"evidence_gathering"},
    "evidence_gathering": {"merchant_response_window", "decision"},
    "merchant_response_window": {"decision"},
    "decision": {"resolved", "escalated"},
    "escalated": {"resolved"},
    "resolved": {"appealed", "final"},
    "appealed": {"decision"},          # representment re-enters the loop
    "final": set(),
}


class InvalidTransition(Exception):
    pass


def advance(current: str, target: str) -> str:
    if target not in TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"{current} -> {target} is not a legal transition")
    return target


def is_terminal(state: str) -> bool:
    return state == "final"
