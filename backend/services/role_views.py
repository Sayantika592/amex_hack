"""Three role-based views (TDD §16). Same decision, three projections."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.db.models import (AnalystAction, Decision, Dispute, EvidenceItem,
                               MerchantResponse, PipelineRun, to_dict)
from backend.taxonomy.registry import get_registry

STATE_STEPS = ["filed", "evidence_gathering", "merchant_response_window",
               "decision", "resolved"]

ACTION_LABELS = {
    "auto_approve": "Resolved in your favour",
    "auto_deny": "Dispute not upheld",
    "escalate_to_analyst": "Under specialist review",
    "request_more_evidence": "More information needed",
    "represent_chargeback": "Merchant contest in progress",
}


def _latest_decision(session, dispute_id: str) -> Optional[Decision]:
    return (session.query(Decision).filter_by(dispute_id=dispute_id)
            .order_by(Decision.decided_at.desc()).first())


def _latest_run(session, dispute_id: str) -> Optional[PipelineRun]:
    return (session.query(PipelineRun).filter_by(dispute_id=dispute_id)
            .order_by(PipelineRun.started_at.desc()).first())


def _progress(state: str) -> List[Dict[str, Any]]:
    idx = STATE_STEPS.index(state) if state in STATE_STEPS else len(STATE_STEPS) - 1
    if state in ("escalated", "appealed", "final"):
        idx = len(STATE_STEPS) - 1
    return [{"step": s, "done": i <= idx} for i, s in enumerate(STATE_STEPS)]


def _category_label(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    t = get_registry().get(code)
    return f"{code} — {t.label}" if t and getattr(t, "label", None) else code


def card_member_view(session, dispute: Dispute) -> Dict[str, Any]:
    dec = _latest_decision(session, dispute.id)
    explanation = (dec.explanation or {}) if dec else {}
    factors = explanation.get("detailed_factors") or []
    view = {
        "role": "card_member",
        "dispute_id": dispute.id,
        "amount": dispute.amount,
        "currency": dispute.currency,
        "status_label": ACTION_LABELS.get(dispute.action or "", "In progress"),
        "state": dispute.state,
        "progress": _progress(dispute.state),
        "category": _category_label(dispute.classified_code),
        "decision_statement": explanation.get("decision_statement"),
        "confidence_pct": explanation.get("confidence_pct"),
        "why": [
            {"text": f.get("text"), "weight_pct": int(round((f.get("weight") or 0) * 100))}
            for f in factors
        ],
        "burden_of_proof": explanation.get("burden_of_proof"),
        "refund_amount": None,
        "what_we_need_from_you": [],
        "can_escalate": dispute.action in ("auto_deny", "represent_chargeback"),
    }
    run = _latest_run(session, dispute.id)
    if run:
        act = (run.stages or {}).get("action", {})
        view["refund_amount"] = act.get("refund_amount")
        view["refund_note"] = act.get("refund_note")
        req = (run.stages or {}).get("evidence_mapping", {})
        if dispute.action == "request_more_evidence":
            view["what_we_need_from_you"] = (req.get("primary") or {}).get(
                "cardholder_requested", [])
    return view


def merchant_view(session, dispute: Dispute) -> Dict[str, Any]:
    dec = _latest_decision(session, dispute.id)
    run = _latest_run(session, dispute.id)
    stages = (run.stages or {}) if run else {}
    scoring = (stages.get("evidence_scoring") or {}).get("items", {})
    mapping = stages.get("evidence_mapping") or {}
    collection = stages.get("evidence_collection") or {}
    explanation = (dec.explanation or {}) if dec else {}
    strength_bars = [
        {"evidence": k, "strength_pct": int(round((v.get("final_strength") or 0) * 100)),
         "label": v.get("strength_label")}
        for k, v in scoring.items()
    ]
    missing = collection.get("missing_required") or []
    for m in missing:
        strength_bars.append({"evidence": m, "strength_pct": 0, "label": "missing"})
    return {
        "role": "merchant",
        "dispute_id": dispute.id,
        "amount": dispute.amount,
        "currency": dispute.currency,
        "state": dispute.state,
        "outcome": dispute.outcome,
        "decision_statement": explanation.get("decision_statement"),
        "category": _category_label(dispute.classified_code),
        "network_reason_codes": dispute.network_reason_codes or [],
        "evidence_strength_bars": strength_bars,
        "what_would_help": (mapping.get("primary") or {}).get("merchant_requested", []),
        "response_window": {
            "responded": bool(dispute.merchant_responded),
            "notified_date": dispute.merchant_notified_date.isoformat()
            if dispute.merchant_notified_date else None,
        },
        "can_represent": dispute.state == "resolved"
        and dispute.outcome == "favor_cardholder",
        "burden_of_proof": explanation.get("burden_of_proof"),
    }


def analyst_view(session, dispute: Dispute) -> Dict[str, Any]:
    dec = _latest_decision(session, dispute.id)
    run = _latest_run(session, dispute.id)
    stages = (run.stages or {}) if run else {}
    evidence_rows = session.query(EvidenceItem).filter_by(dispute_id=dispute.id).all()
    responses = session.query(MerchantResponse).filter_by(dispute_id=dispute.id).all()
    overrides = session.query(AnalystAction).filter_by(dispute_id=dispute.id).all()
    decision_stage = stages.get("decision") or {}
    return {
        "role": "analyst",
        "dispute": to_dict(dispute),
        "category": _category_label(dispute.classified_code),
        "pipeline_stages": stages,
        "factor_breakdown": (dec.factor_breakdown if dec else None),
        "integrity_signals": (dec.integrity if dec else None),
        "compliance": (dec.compliance if dec else None),
        "explanation": (dec.explanation if dec else None),
        "burden_of_proof": (dec.burden if dec else None),
        "fairness": decision_stage.get("fairness"),
        "counterfactual_note": "Decision inputs are demographically blinded; "
                               "re-running with party attributes swapped produces "
                               "the identical factor breakdown (see fairness block).",
        "evidence_items": [to_dict(e) for e in evidence_rows],
        "merchant_responses": [to_dict(r) for r in responses],
        "analyst_actions": [to_dict(a) for a in overrides],
        "override_controls": ["accept", "modify", "override"],
    }
