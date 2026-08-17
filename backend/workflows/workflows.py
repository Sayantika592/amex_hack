"""Post-decision workflows: merchant response, representment, analyst override,
and merchant-response-window expiry. Each records the event, updates state,
and (where the spec requires) re-runs the pipeline against the enlarged
evidence base.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import yaml

from backend.db.models import (AnalystAction, Dispute, EvidenceItem,
                               FeedbackEvent, MerchantResponse)
from backend.paths import CONFIG_DIR
from backend.pipeline import orchestrator
from backend.pipeline.layer9_feedback import record_feedback


def _now():
    return datetime.now(timezone.utc)


def _add_evidence(session, dispute_id: str, items: List[Dict[str, Any]],
                  source_party: str) -> List[str]:
    ids = []
    for item in items or []:
        eid = f"EV-{uuid.uuid4().hex[:10]}"
        session.add(EvidenceItem(
            id=eid,
            dispute_id=dispute_id,
            evidence_type=item.get("evidence_type", "merchant_statement"),
            source_party=source_party,
            payload=item.get("payload", {}),
            dated=item.get("dated", True),
            age_days=item.get("age_days", 0),
        ))
        ids.append(eid)
    session.flush()
    return ids


async def submit_merchant_response(session, dispute: Dispute,
                                   statement: str,
                                   evidence: Optional[List[Dict[str, Any]]] = None,
                                   response_type: str = "contest"):
    """Merchant responds inside the window -> evidence stored -> pipeline re-runs."""
    ev_ids = _add_evidence(session, dispute.id, evidence, "merchant")
    session.add(MerchantResponse(
        id=f"MR-{uuid.uuid4().hex[:10]}",
        dispute_id=dispute.id,
        responded_at=_now(),
        response_type=response_type,
        statement=statement,
        evidence_refs=ev_ids,
        is_representment=False,
    ))
    dispute.merchant_responded = True
    session.flush()
    if response_type == "accept":
        dispute.outcome = "favor_cardholder"
        dispute.action = "auto_approve"
        dispute.state = "resolved"
        dispute.resolved_date = _now()
        record_feedback(session, dispute.id, "issuer_decision",
                        {"outcome": "favor_cardholder", "via": "merchant_accept"})
        session.flush()
        return None
    return await orchestrator.run_pipeline(session, dispute, trigger="merchant_response")


async def file_representment(session, dispute: Dispute, statement: str,
                             evidence: Optional[List[Dict[str, Any]]] = None):
    """Merchant contests a resolved dispute -> appealed -> pipeline re-runs."""
    if dispute.state not in ("resolved",):
        raise ValueError(f"Representment requires a resolved dispute (state={dispute.state})")
    ev_ids = _add_evidence(session, dispute.id, evidence, "merchant")
    session.add(MerchantResponse(
        id=f"MR-{uuid.uuid4().hex[:10]}",
        dispute_id=dispute.id,
        responded_at=_now(),
        response_type="contest",
        statement=statement,
        evidence_refs=ev_ids,
        is_representment=True,
    ))
    dispute.merchant_responded = True
    prior_outcome = dispute.outcome
    session.flush()
    ctx = await orchestrator.run_pipeline(session, dispute, trigger="representment")
    new_outcome = dispute.outcome
    record_feedback(session, dispute.id, "representment_result", {
        "prior_outcome": prior_outcome,
        "new_outcome": new_outcome,
        "merchant_won": new_outcome != prior_outcome and "merchant" in (new_outcome or ""),
    })
    session.flush()
    return ctx


def analyst_override(session, dispute: Dispute, action: str,
                     new_outcome: Optional[str], reason: str,
                     analyst_id: str = "analyst-demo") -> Dict[str, Any]:
    """Analyst accepts / modifies / overrides an escalated or resolved case.
    The recorded reason feeds the learning loop (Layer 9)."""
    if action not in ("accept", "modify", "override"):
        raise ValueError("action must be accept|modify|override")
    row = AnalystAction(
        id=f"AA-{uuid.uuid4().hex[:10]}",
        dispute_id=dispute.id,
        analyst_id=analyst_id,
        action=action,
        new_outcome=new_outcome,
        reason=reason,
    )
    session.add(row)
    system_outcome = dispute.outcome
    if action == "accept":
        if dispute.state == "escalated":
            dispute.state = "resolved"
            dispute.resolved_date = _now()
        final_outcome = system_outcome
    else:
        if not new_outcome:
            raise ValueError("modify/override requires new_outcome")
        dispute.outcome = new_outcome
        if dispute.state in ("escalated", "decision"):
            dispute.state = "resolved"
        dispute.resolved_date = _now()
        final_outcome = new_outcome
    record_feedback(session, dispute.id, "analyst_override", {
        "analyst_action": action,
        "system_outcome": system_outcome,
        "final_outcome": final_outcome,
        "reason": reason,
        "trains": "classifier_edge_cases",
    })
    session.flush()
    return {"analyst_action_id": row.id, "final_outcome": final_outcome,
            "state": dispute.state}


def _response_window_days(network: str) -> int:
    with open(CONFIG_DIR / "network_rules.yaml") as f:
        rules = yaml.safe_load(f)
    return rules["networks"].get(network, rules["networks"]["amex"])[
        "merchant_response_window_days"]


async def expire_merchant_windows(session) -> List[str]:
    """Window-expiry job: disputes waiting on the merchant past the network
    window are re-run; Layer 7's merchant_no_response override then
    auto-favours the card member ('no proof provided')."""
    expired: List[str] = []
    q = session.query(Dispute).filter(
        Dispute.state == "merchant_response_window",
        Dispute.merchant_responded == False,  # noqa: E712
    )
    for d in q.all():
        if not d.merchant_notified_date:
            continue
        window = _response_window_days(d.network or "amex")
        notified = d.merchant_notified_date
        if notified.tzinfo is None:
            notified = notified.replace(tzinfo=timezone.utc)
        if _now() - notified > timedelta(days=window):
            await orchestrator.run_pipeline(session, d, trigger="initial")
            expired.append(d.id)
    return expired
