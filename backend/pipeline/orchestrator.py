"""Orchestrator — runs the 10-layer pipeline end to end for one dispute.

Responsibilities:
  * build the PipelineContext from a Dispute row
  * run layers 0..9 in order, timing each and publishing SSE events
  * compose the human-readable explanation (Layer 7 output + Layer 8 action)
  * advance the dispute lifecycle state machine
  * persist PipelineRun + Decision + updated Dispute fields
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.db.models import Decision, Dispute, PipelineRun
from backend.lifecycle import state_machine as sm
from backend.pipeline import (
    layer0_graph,
    layer1_classification,
    layer2_evidence_mapping,
    layer3_collection,
    layer4_scoring,
    layer5_integrity,
    layer6_decision,
    layer7_compliance,
    layer8_action,
    layer9_feedback,
)
from backend.pipeline.context import PipelineContext
from backend.services.events import bus

STAGE_SEQUENCE = [
    ("graph_context", "Layer 0 — Knowledge Graph", layer0_graph.run),
    ("classification", "Layer 1 — Classification", layer1_classification.run),
    ("evidence_mapping", "Layer 2 — Evidence Mapping", layer2_evidence_mapping.run),
    ("evidence_collection", "Layer 3 — Dynamic Collection", layer3_collection.run),
    ("evidence_scoring", "Layer 4 — Evidence Scoring", layer4_scoring.run),
    ("integrity", "Layer 5 — Dispute Integrity", layer5_integrity.run),
    ("decision", "Layer 6 — Decision Model", layer6_decision.run),
    ("compliance", "Layer 7 — Reasoning & Compliance", layer7_compliance.run),
    ("action", "Layer 8 — Action Recommendation", layer8_action.run),
    ("feedback", "Layer 9 — Feedback Loop", layer9_feedback.run),
]


def _days_since_purchase(d: Dispute) -> Optional[float]:
    try:
        txn_ts = d.transaction.timestamp if d.transaction else None
        if txn_ts and d.filed_date:
            return round((d.filed_date - txn_ts).total_seconds() / 86400.0, 2)
    except Exception:
        pass
    return None


def dispute_to_dict(d: Dispute) -> Dict[str, Any]:
    return {
        "id": d.id,
        "network": d.network,
        "description": d.description or "",
        "user_selected_code": d.user_selected_code,
        "classified_code": d.classified_code,
        "transaction_id": d.transaction_id,
        "merchant_id": d.merchant_id,
        "card_member_id": d.card_member_id,
        "amount": d.amount,
        "currency": d.currency,
        "filed_date": d.filed_date.isoformat() if d.filed_date else None,
        "merchant_notified_date": d.merchant_notified_date.isoformat() if d.merchant_notified_date else None,
        "merchant_responded": bool(d.merchant_responded),
        "days_since_purchase": _days_since_purchase(d),
        "state": d.state,
    }


async def _emit(dispute_id: str, stage: str, name: str, status: str,
                payload: Optional[Dict[str, Any]] = None) -> None:
    bus.publish(dispute_id, {
        "stage": stage,
        "name": name,
        "status": status,
        "payload_summary": payload or {},
    })
    await asyncio.sleep(0)  # let subscribers drain between stages


def _payload_summary(stage: str, out: Dict[str, Any]) -> Dict[str, Any]:
    """Small, safe summary per stage for the live event stream."""
    if stage == "classification":
        return {
            "primary_code": out.get("primary_code"),
            "primary_label": out.get("primary_label"),
            "confidence": out.get("confidence"),
            "status": out.get("status"),
            "override": out.get("override"),
            "model": out.get("model"),
            "mode": out.get("mode"),
        }
    if stage == "graph_context":
        return {
            "prior_disputes": len(out.get("prior_disputes") or []),
            "merchant_dispute_rate": out.get("merchant_dispute_rate"),
            "existing_refund": bool(out.get("existing_refund")),
        }
    if stage == "evidence_mapping":
        return {"required": out.get("union_required"), "network": out.get("network")}
    if stage == "evidence_collection":
        return {
            "collected": sorted((out.get("collected") or {}).keys()),
            "missing_required": out.get("missing_required"),
            "completeness": out.get("completeness"),
        }
    if stage == "evidence_scoring":
        scored = out.get("scored") or {}
        return {k: v.get("strength_label") for k, v in scored.items()}
    if stage == "integrity":
        return {
            "suspicion_score": out.get("suspicion_score"),
            "is_suspicious": out.get("is_suspicious"),
            "signals": [s.get("signal") for s in out.get("signals") or []],
        }
    if stage == "decision":
        return {
            "final_score": out.get("final_score"),
            "composite_score": out.get("composite_score"),
            "multi_category": out.get("multi_category"),
            "conflict_hold": out.get("conflict_hold"),
        }
    if stage == "compliance":
        return {
            "overrides": [o.get("rule") for o in out.get("overrides") or []],
            "notes": [n.get("rule") for n in out.get("compliance_notes") or []],
        }
    if stage == "action":
        return {
            "action": out.get("action"),
            "reason": out.get("reason"),
            "confidence": out.get("confidence"),
            "refund_amount": out.get("refund_amount"),
        }
    if stage == "feedback":
        return {"recorded": out.get("recorded"), "event_id": out.get("event_id")}
    return {}


async def run_pipeline(session, dispute: Dispute, trigger: str = "initial") -> PipelineContext:
    """Run the full pipeline for one dispute and persist everything."""
    ctx = PipelineContext(dispute=dispute_to_dict(dispute), session=session, trigger=trigger)
    dispute_id = dispute.id

    # lifecycle: (re)enter the pipeline
    if trigger == "initial" and dispute.state == "filed":
        pass
    elif trigger in ("merchant_response", "representment", "analyst") and dispute.state in ("resolved", "appealed", "escalated", "merchant_response_window"):
        if dispute.state == "resolved":
            dispute.state = sm.advance(dispute.state, "appealed")
        if dispute.state == "appealed":
            dispute.state = sm.advance(dispute.state, "decision")

    await _emit(dispute_id, "pipeline", "Pipeline", "started", {"trigger": trigger})

    for stage, name, fn in STAGE_SEQUENCE:
        await _emit(dispute_id, stage, name, "running")
        t0 = time.time()
        try:
            if asyncio.iscoroutinefunction(fn):
                out = await fn(ctx)
            else:
                out = fn(ctx)
        except Exception as exc:  # keep pipeline debuggable, never half-persist silently
            out = {"error": str(exc)}
            ctx.stages[stage] = out
            ctx.timings[stage] = time.time() - t0
            await _emit(dispute_id, stage, name, "error", {"error": str(exc)})
            raise
        ctx.stages[stage] = out
        ctx.timings[stage] = time.time() - t0

        # lifecycle transitions tied to stage completions
        if stage == "classification" and dispute.state == "filed":
            dispute.state = sm.advance(dispute.state, "evidence_gathering")
        if stage == "evidence_collection" and dispute.state == "evidence_gathering":
            dispute.state = sm.advance(dispute.state, "merchant_response_window")
        if stage == "integrity" and dispute.state == "merchant_response_window":
            dispute.state = sm.advance(dispute.state, "decision")

        await _emit(dispute_id, stage, name, "complete", _payload_summary(stage, out))

    # compose reasoning (Layer 7 explanation needs the Layer 8 action)
    decision_out = ctx.stage("decision")
    compliance_out = ctx.stage("compliance")
    action_out = ctx.stage("action")
    reasoning = layer7_compliance.generate_explanation(
        decision_out, compliance_out, action_out, ctx.dispute.get("network", "amex"))
    ctx.stages["reasoning"] = reasoning
    await _emit(dispute_id, "reasoning", "Layer 7 — Explanation", "complete",
                {"decision_statement": reasoning.get("decision_statement"),
                 "confidence_pct": reasoning.get("confidence_pct")})

    # lifecycle: terminal-ish transitions from the action
    action = action_out.get("action")
    if action in ("auto_approve", "auto_deny"):
        outcome = "favor_cardholder" if action == "auto_approve" else "favor_merchant"
        if dispute.state in ("decision", "escalated"):
            dispute.state = sm.advance(dispute.state, "resolved")
        dispute.outcome = outcome
    elif action == "escalate_to_analyst":
        if dispute.state == "decision":
            dispute.state = sm.advance(dispute.state, "escalated")
        dispute.outcome = "escalated"
    elif action == "represent_chargeback":
        if dispute.state == "decision":
            dispute.state = sm.advance(dispute.state, "resolved")
        dispute.outcome = "favor_merchant_representment_offered"
    else:  # request_more_evidence
        dispute.state = "evidence_gathering"
        dispute.outcome = "pending_more_evidence"

    # persist dispute fields
    cls = ctx.stage("classification")
    dispute.classified_code = cls.get("primary_code")
    dispute.classification_confidence = cls.get("confidence")
    dispute.network_reason_codes = (cls.get("network_mapping") or {}).get("network_reason_codes", [])
    dispute.action = action
    dispute.final_score = decision_out.get("final_score")
    if dispute.state in ("resolved", "escalated"):
        dispute.resolved_date = datetime.now(timezone.utc)

    # persist Decision row
    dec_row = Decision(
        id=f"DEC-{uuid.uuid4().hex[:10]}",
        dispute_id=dispute_id,
        decided_at=datetime.now(timezone.utc),
        final_score=decision_out.get("final_score"),
        action=action,
        outcome=dispute.outcome,
        confidence=action_out.get("confidence"),
        factor_breakdown=decision_out.get("factor_breakdown"),
        burden=decision_out.get("burden_of_proof"),
        integrity=ctx.stage("integrity"),
        compliance=compliance_out,
        explanation=reasoning,
        decided_by="system",
        is_representment=(trigger == "representment"),
    )
    session.add(dec_row)

    # persist PipelineRun (full machine-readable record)
    run_row = PipelineRun(
        id=f"RUN-{uuid.uuid4().hex[:10]}",
        dispute_id=dispute_id,
        started_at=datetime.fromtimestamp(ctx.started_at, tz=timezone.utc),
        finished_at=datetime.now(timezone.utc),
        stages=json.loads(json.dumps(ctx.as_record(), default=str)),
        trigger=trigger,
    )
    session.add(run_row)
    session.flush()

    await _emit(dispute_id, "pipeline", "Pipeline", "complete", {
        "action": action,
        "outcome": dispute.outcome,
        "final_score": decision_out.get("final_score"),
        "elapsed_seconds": round(ctx.elapsed, 3),
    })
    return ctx


def run_pipeline_sync(session, dispute: Dispute, trigger: str = "initial") -> PipelineContext:
    """Synchronous wrapper for scripts / evaluation (no running event loop)."""
    return asyncio.run(run_pipeline(session, dispute, trigger))
