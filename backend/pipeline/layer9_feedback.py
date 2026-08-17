"""Layer 9 — feedback & learning loop.

Records outcome signals (issuer decisions, representment results, analyst
overrides, cardholder escalations, resolution time) and produces the weekly
accuracy report + retraining trigger / threshold-recalibration suggestions.
The system learns from actual resolutions, not just its own predictions.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from backend.db import models as m
from backend.db.database import session_scope
from backend.pipeline.layer8_action import thresholds


def record_feedback(session, dispute_id: str, signal_type: str, payload: dict) -> str:
    """Append a feedback signal. Uses the caller's session when given (so it
    joins the pipeline transaction); otherwise opens its own."""
    fid = f"FB-{uuid.uuid4().hex[:10]}"
    row = m.FeedbackEvent(id=fid, dispute_id=dispute_id,
                          signal_type=signal_type, payload=payload)
    if session is not None:
        session.add(row)
        session.flush()
    else:
        with session_scope() as db:
            db.add(row)
    return fid


def run(ctx) -> dict:
    action = ctx.stages["action"]
    elapsed = ctx.elapsed
    fid = record_feedback(ctx.session, ctx.dispute["id"], "issuer_decision", {
        "outcome": action["outcome"], "action": action["action"],
        "final_score": action["final_score"],
        "confidence": action.get("confidence"),
        "resolution_seconds": round(elapsed, 3),
        "trigger": ctx.trigger,
    })
    return {"feedback_event_id": fid, "signals_recorded": ["issuer_decision"],
            "resolution_seconds": round(elapsed, 3),
            "loop": "Outcome recorded; representment results, analyst overrides "
                    "and escalations append further signals that recalibrate "
                    "thresholds and retrain the classifier."}


def weekly_accuracy_report() -> dict:
    """Aggregates analyst overrides & representment reversals per category;
    categories whose implied accuracy drops below the configured floor are
    flagged for retraining."""
    floor = thresholds()["retraining"]["accuracy_floor"]
    per_cat = defaultdict(lambda: {"decisions": 0, "overrides": 0, "reversals": 0})
    with session_scope() as db:
        for d in db.query(m.Decision).all():
            dispute = db.get(m.Dispute, d.dispute_id)
            cat = (dispute.classified_code if dispute else None) or "UNKNOWN"
            per_cat[cat]["decisions"] += 1
        for a in db.query(m.AnalystAction).filter(m.AnalystAction.action == "override").all():
            dispute = db.get(m.Dispute, a.dispute_id)
            cat = (dispute.classified_code if dispute else None) or "UNKNOWN"
            per_cat[cat]["overrides"] += 1
        for f in db.query(m.FeedbackEvent).filter(
                m.FeedbackEvent.signal_type == "representment_result").all():
            if (f.payload or {}).get("reversed"):
                dispute = db.get(m.Dispute, f.dispute_id)
                cat = (dispute.classified_code if dispute else None) or "UNKNOWN"
                per_cat[cat]["reversals"] += 1
    report = {}
    for cat, s in per_cat.items():
        n = max(s["decisions"], 1)
        implied_acc = 1 - (s["overrides"] + s["reversals"]) / n
        report[cat] = {**s, "implied_accuracy": round(implied_acc, 3),
                       "retraining_triggered": implied_acc < floor and s["decisions"] >= 10}
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "accuracy_floor": floor, "categories": report,
            "retraining_candidates": [c for c, v in report.items()
                                       if v["retraining_triggered"]]}
