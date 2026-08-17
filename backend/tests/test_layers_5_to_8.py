"""Layers 5-8: integrity (advisory only), decision bands + conclusive
evidence, compliance overrides, action recommendation."""
from datetime import datetime, timedelta, timezone

from backend.pipeline.context import PipelineContext
from backend.pipeline.layer6_decision import run as decision_run
from backend.pipeline.layer7_compliance import check_compliance
from backend.pipeline.layer8_action import recommend_action

NOW = datetime.now(timezone.utc)


def _decision(score, **extra):
    return {"final_score": score, "composite_score": score,
            "category": "QD-01", "factor_breakdown": {}, "conflicts": [],
            "conflict_hold": False, "conclusive_evidence": [], **extra}


def _integrity(susp=0.0):
    return {"suspicion_score": susp, "signals": [],
            "is_suspicious": susp > 0.5,
            "action": "flag_for_review" if susp > 0.5 else "proceed_normally"}


def _evidence(completeness=1.0, missing=None):
    return {"completeness": completeness, "missing_required": missing or [],
            "collected": {}}


DISPUTE = {"id": "D-T", "amount": 1000.0, "currency": "INR"}


# ---------------------------------------------------------------- layer 8
def test_action_bands():
    assert recommend_action(_decision(0.8), _integrity(), {}, _evidence(),
                            DISPUTE)["action"] == "auto_approve"
    assert recommend_action(_decision(0.45), _integrity(), {}, _evidence(),
                            DISPUTE)["action"] == "auto_approve"
    mid = recommend_action(_decision(0.0), _integrity(), {}, _evidence(),
                           DISPUTE)
    assert mid["action"] in ("request_more_evidence", "escalate_to_analyst")
    assert recommend_action(_decision(-0.5), _integrity(), {}, _evidence(),
                            DISPUTE)["action"] == "represent_chargeback"
    assert recommend_action(_decision(-0.85), _integrity(), {}, _evidence(),
                            DISPUTE)["action"] == "auto_deny"


def test_integrity_flag_never_auto_denies():
    """Advisory only: even with cardholder-unfavourable evidence, a
    suspicious dispute escalates to a human, never auto-denies."""
    out = recommend_action(_decision(-0.9), _integrity(0.8), {}, _evidence(),
                           DISPUTE)
    assert out["action"] == "escalate_to_analyst"
    out2 = recommend_action(_decision(0.9), _integrity(0.8), {}, _evidence(),
                            DISPUTE)
    assert out2["action"] == "escalate_to_analyst"


def test_compliance_override_beats_evidence():
    comp = {"overrides": [{"rule": "merchant_no_response",
                           "effect": "auto_favor_cardholder",
                           "reason": "no response in window"}]}
    out = recommend_action(_decision(-0.9), _integrity(), comp, _evidence(),
                           DISPUTE)
    assert out["action"] == "auto_approve"
    assert out["reason"] == "compliance_override"


def test_incomplete_evidence_requests_more():
    out = recommend_action(_decision(0.9), _integrity(), {},
                           _evidence(0.3, ["shipping_tracking"]), DISPUTE)
    assert out["action"] == "request_more_evidence"


def test_conclusive_evidence_bypasses_completeness_gate():
    d = _decision(0.75, conclusive_evidence=[
        {"factor": "transaction_pattern", "reason": "duplicate_within_5_min",
         "floor": 0.72}])
    out = recommend_action(d, _integrity(), {}, _evidence(0.3), DISPUTE)
    assert out["action"] == "auto_approve"


def test_conflict_hold_requests_clarification():
    d = _decision(0.8, conflict_hold=True,
                  conflicts=[{"conflict": "NR-01 vs QD-01"}])
    out = recommend_action(d, _integrity(), {}, _evidence(), DISPUTE)
    assert out["action"] == "request_more_evidence"
    assert out["reason"] == "conflicting_sub_claims"


def test_auto_approve_carries_refund():
    out = recommend_action(_decision(0.8), _integrity(), {}, _evidence(),
                           DISPUTE)
    assert out["refund_amount"] == 1000.0


# ---------------------------------------------------------------- layer 7
def _graph(txn_days_ago=10):
    return {"transaction": {
        "timestamp": (NOW - timedelta(days=txn_days_ago)).isoformat()}}


def test_merchant_no_response_override():
    dispute = {"merchant_responded": False,
               "merchant_notified_date": (NOW - timedelta(days=25)).isoformat(),
               "filed_date": (NOW - timedelta(days=26)).isoformat()}
    out = check_compliance(dispute, _decision(0), _evidence(), _graph(30),
                           "amex")
    assert any(o["rule"] == "merchant_no_response" for o in out["overrides"])
    # visa window is 30 days -> same silence does NOT override yet
    out_visa = check_compliance(dispute, _decision(0), _evidence(),
                                _graph(30), "visa")
    assert not any(o["rule"] == "merchant_no_response"
                   for o in out_visa["overrides"])


def test_chargeback_time_limit():
    dispute = {"merchant_responded": True,
               "filed_date": NOW.isoformat()}
    out = check_compliance(dispute, _decision(0), _evidence(), _graph(200),
                           "amex")
    assert any(o["effect"] == "deny_chargeback" for o in out["overrides"])


# ---------------------------------------------------------------- layer 6
def _ctx(code, scored=None, categories=None):
    ctx = PipelineContext(dispute={"id": "D-T", "network": "amex",
                                   "amount": 1000.0})
    ctx.stages["classification"] = {
        "status": "auto_classified", "primary_code": code, "confidence": 0.9,
        "categories": categories or [{"code": code, "confidence": 0.9}]}
    ctx.stages["evidence_scoring"] = {"scored": scored or {}}
    ctx.stages["graph_context"] = {"prior_disputes": [],
                                   "merchant_dispute_rate": 0.02,
                                   "merchant_dispute_ct": 0,
                                   "merchant_loss_rate": 0.0}
    return ctx


def test_conclusive_duplicate_floors_score():
    scored = {"related_transactions": {
        "data": {"transactions": [
            {"id": "T-1", "amount": 1000.0, "merchant_id": "M-1",
             "timestamp": (NOW - timedelta(seconds=90)).isoformat()}],
            "disputed_transaction": {"id": "T-0", "amount": 1000.0, "merchant_id": "M-1",
                         "timestamp": NOW.isoformat()}},
        "final_strength": 0.8, "strength_label": "strong"}}
    out = decision_run(_ctx("BA-01", scored))
    assert out["conclusive_evidence"], "duplicate should be conclusive"
    assert out["composite_score"] >= 0.72


def test_demographic_blindness_fields_absent():
    """Layer 6 must never see name / tier / demographic fields."""
    ctx = _ctx("QD-01")
    ctx.dispute.update({"card_member_name": "X", "card_tier": "platinum"})
    out = decision_run(ctx)
    import json
    blob = json.dumps(out)
    assert "platinum" not in blob and "card_member_name" not in blob
