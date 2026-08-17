"""Lifecycle state machine (TDD §14) and full-pipeline workflow behaviour."""
import pytest

from backend.lifecycle import state_machine as sm


def test_legal_transitions():
    s = sm.advance("filed", "evidence_gathering")
    s = sm.advance(s, "merchant_response_window")
    s = sm.advance(s, "decision")
    s = sm.advance(s, "resolved")
    s = sm.advance(s, "appealed")          # representment
    s = sm.advance(s, "decision")          # re-enters the loop
    s = sm.advance(s, "resolved")
    s = sm.advance(s, "final")
    assert sm.is_terminal(s)


def test_illegal_transitions_raise():
    with pytest.raises(sm.InvalidTransition):
        sm.advance("filed", "resolved")
    with pytest.raises(sm.InvalidTransition):
        sm.advance("final", "decision")
    with pytest.raises(sm.InvalidTransition):
        sm.advance("resolved", "evidence_gathering")


def test_demo_pipeline_outcomes(db):
    """Each seeded demo case lands on its designed outcome via the REAL
    pipeline (regression net for the whole system)."""
    from backend.db.models import Dispute
    from backend.pipeline.orchestrator import run_pipeline_sync

    expected = {
        "D-DEMO-RAHUL": ("auto_approve", None),
        "D-DEMO-DUP": ("auto_approve", None),
        "D-DEMO-SUB": ("auto_approve", None),
        "D-DEMO-NORESP": ("auto_approve", "compliance_override"),
        "D-DEMO-CONFLICT": ("request_more_evidence", "conflicting_sub_claims"),
        "D-DEMO-VAGUE": ("request_more_evidence", None),
        "D-DEMO-FRAUD": ("escalate_to_analyst", None),
        "D-DEMO-MOOT": ("auto_deny", "compliance_override"),
    }
    for did, (want_action, want_reason) in expected.items():
        d = db.get(Dispute, did)
        assert d is not None, f"{did} not seeded"
        ctx = run_pipeline_sync(db, d, trigger="initial")
        act = ctx.stage("action")
        assert act.get("action") == want_action, (did, act)
        if want_reason:
            assert act.get("reason") == want_reason, (did, act)


def test_integrity_case_is_never_auto_denied(db):
    from backend.db.models import Dispute
    from backend.pipeline.orchestrator import run_pipeline_sync
    d = db.get(Dispute, "D-DEMO-FRAUD")
    ctx = run_pipeline_sync(db, d, trigger="initial")
    assert ctx.stage("integrity")["suspicion_score"] > 0.5
    assert ctx.stage("action")["action"] == "escalate_to_analyst"
    assert ctx.stage("action")["action"] != "auto_deny"
