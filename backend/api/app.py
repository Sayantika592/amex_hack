"""FastAPI backend for the Frictionless Dispute & Chargeback Resolution system."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func

from backend.config import settings
from backend.db.database import SessionLocal
from backend.db.models import (Decision, Dispute, EvidenceItem, FeedbackEvent,
                               Merchant, PipelineRun, Transaction, to_dict)
from backend.graph.graph import graph_info
from backend.paths import GENERATED_DATA_DIR
from backend.models.classification.factory import classifier_info
from backend.nlp.factory import nlp_info
from backend.pipeline import orchestrator
from backend.pipeline.layer9_feedback import record_feedback, weekly_accuracy_report
from backend.queueing.queue import queue_info
from backend.services import role_views
from backend.services.events import bus
from backend.taxonomy.registry import get_registry
from backend.vision.adapters import vision_info
from backend.workflows import workflows

app = FastAPI(title="Frictionless Dispute & Chargeback Resolution",
              version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:4173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ----------------------------------------------------------------- schemas
class EvidenceIn(BaseModel):
    evidence_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    dated: bool = True
    age_days: int = 0


class NewDispute(BaseModel):
    transaction_id: str
    user_selected_code: Optional[str] = None
    description: str
    network: Optional[str] = None
    evidence: List[EvidenceIn] = Field(default_factory=list)


class MerchantResponseIn(BaseModel):
    statement: str
    response_type: str = "contest"          # contest|accept
    evidence: List[EvidenceIn] = Field(default_factory=list)


class RepresentmentIn(BaseModel):
    statement: str
    evidence: List[EvidenceIn] = Field(default_factory=list)


class AnalystOverrideIn(BaseModel):
    action: str                              # accept|modify|override
    new_outcome: Optional[str] = None
    reason: str
    analyst_id: str = "analyst-demo"


class EscalationIn(BaseModel):
    reason: str = ""


# -------------------------------------------------------------------- meta
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/meta/models")
def meta_models():
    """Honest REAL/DEMO mode per model component (spec requirement)."""
    return {
        "ai_mode_setting": settings.ai_mode,
        "components": {
            "classifier": classifier_info(),
            "nlp": nlp_info(),
            "vision": vision_info(),
            "graph": graph_info(),
            "queue": queue_info(),
            "nlg": {
                "component": "constrained_nlg",
                "mode": "demo",
                "detail": "Template-based constrained NLG (rule engine emits facts; "
                          "templates rephrase). A local/remote LLM is an optional "
                          "upgrade, never a dependency.",
            },
        },
    }


@app.get("/api/meta/thresholds")
def meta_thresholds():
    """Decision bands and gates from config — so the UI can show scores
    against their governing thresholds instead of hardcoding numbers."""
    import yaml
    from backend.paths import CONFIG_DIR
    cfg = yaml.safe_load((CONFIG_DIR / "decision_thresholds.yaml").read_text())
    return {
        "score_bands": cfg.get("score_bands", {}),
        "integrity": cfg.get("integrity", {}),
        "evidence": cfg.get("evidence", {}),
        "conclusive_floors": cfg.get("conclusive_floors", {}),
        "source": "config/decision_thresholds.yaml",
    }


@app.get("/api/meta/taxonomy")
def meta_taxonomy():
    reg = get_registry()
    return {
        "internal_types": [
            {"code": t.code, "name": t.name, "label": t.label, "macro": t.macro,
             "macro_name": t.macro_name, "in_techdoc": t.in_techdoc,
             "in_excel": t.in_excel, "network_codes": t.network_codes}
            for t in (reg.get(c) for c in reg.all_codes())
        ],
        "one_to_many": reg.one_to_many(),
        "many_to_one": reg.many_to_one(),
    }


# ---------------------------------------------------------------- disputes
@app.get("/api/disputes")
def list_disputes(db=Depends(get_db),
                  state: Optional[str] = None,
                  action: Optional[str] = None,
                  q: Optional[str] = None,
                  demo_only: bool = False,
                  limit: int = Query(50, le=200),
                  offset: int = 0):
    query = db.query(Dispute).filter(Dispute.is_historical == False)  # noqa: E712
    if state:
        query = query.filter(Dispute.state == state)
    if action:
        query = query.filter(Dispute.action == action)
    if q:
        query = query.filter(Dispute.id.contains(q) | Dispute.description.contains(q))
    if demo_only:
        query = query.filter(Dispute.id.startswith("D-DEMO"))
    total = query.count()
    rows = (query.order_by(Dispute.filed_date.desc())
            .offset(offset).limit(limit).all())
    return {"total": total, "items": [to_dict(d) for d in rows]}


@app.get("/api/disputes/{dispute_id}")
def get_dispute(dispute_id: str, db=Depends(get_db)):
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "dispute not found")
    dec = (db.query(Decision).filter_by(dispute_id=dispute_id)
           .order_by(Decision.decided_at.desc()).first())
    run = (db.query(PipelineRun).filter_by(dispute_id=dispute_id)
           .order_by(PipelineRun.started_at.desc()).first())
    return {
        "dispute": to_dict(d),
        "decision": to_dict(dec) if dec else None,
        "pipeline_run": to_dict(run) if run else None,
    }


@app.post("/api/disputes", status_code=201)
async def file_dispute(body: NewDispute, db=Depends(get_db)):
    txn = db.get(Transaction, body.transaction_id)
    if not txn:
        raise HTTPException(404, "transaction not found")
    did = f"D-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc)
    d = Dispute(
        id=did,
        transaction_id=txn.id,
        card_member_id=txn.card_member_id,
        merchant_id=txn.merchant_id,
        network=body.network or txn.network or "amex",
        user_selected_code=body.user_selected_code,
        description=body.description,
        filed_date=now,
        merchant_notified_date=now,
        state="filed",
        amount=txn.amount,
        currency=txn.currency,
    )
    db.add(d)
    for ev in body.evidence:
        db.add(EvidenceItem(
            id=f"EV-{uuid.uuid4().hex[:10]}",
            dispute_id=did,
            evidence_type=ev.evidence_type,
            source_party="cardholder",
            payload=ev.payload,
            dated=ev.dated,
            age_days=ev.age_days,
        ))
    db.flush()
    return {"dispute_id": did, "state": d.state}


@app.post("/api/disputes/{dispute_id}/run")
async def run_dispute(dispute_id: str, db=Depends(get_db)):
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "dispute not found")
    ctx = await orchestrator.run_pipeline(db, d, trigger="initial")
    return {"dispute_id": dispute_id, "action": ctx.stage("action").get("action"),
            "outcome": d.outcome, "state": d.state,
            "final_score": ctx.stage("decision").get("final_score"),
            "record": ctx.as_record()}


@app.get("/api/disputes/{dispute_id}/image/{kind}")
def dispute_image(dispute_id: str, kind: str, db=Depends(get_db)):
    """Serve the actual evidence images the vision pipeline analysed.

    kind = "photo"   -> the card member's uploaded photo
    kind = "listing" -> the merchant's product listing image
    Paths are resolved from the evidence record and must resolve inside the
    generated-images directory (no path traversal).
    """
    etype = {"photo": "cardholder_photos",
             "listing": "product_listing"}.get(kind)
    if not etype:
        raise HTTPException(404, "unknown image kind")
    row = (db.query(EvidenceItem)
             .filter_by(dispute_id=dispute_id, evidence_type=etype).first())
    ref = (row.payload or {}).get("image_ref") if row else None
    if not ref:
        raise HTTPException(404, "no image on this evidence item")
    root = (GENERATED_DATA_DIR / "images").resolve()
    try:
        path = Path(ref).resolve()
        path.relative_to(root)
    except (ValueError, OSError):
        raise HTTPException(404, "image not available for this dispute")
    if not path.exists():
        raise HTTPException(404, "image file missing — regenerate the dataset")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/disputes/{dispute_id}/view/{role}")
def dispute_view(dispute_id: str, role: str, db=Depends(get_db)):
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "dispute not found")
    if role == "card_member":
        return role_views.card_member_view(db, d)
    if role == "merchant":
        return role_views.merchant_view(db, d)
    if role == "analyst":
        return role_views.analyst_view(db, d)
    raise HTTPException(400, "role must be card_member|merchant|analyst")


@app.post("/api/disputes/{dispute_id}/merchant-response")
async def merchant_response(dispute_id: str, body: MerchantResponseIn,
                            db=Depends(get_db)):
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "dispute not found")
    ctx = await workflows.submit_merchant_response(
        db, d, body.statement,
        [e.model_dump() for e in body.evidence], body.response_type)
    return {"dispute_id": dispute_id, "state": d.state, "outcome": d.outcome,
            "re_ran_pipeline": ctx is not None}


@app.post("/api/disputes/{dispute_id}/representment")
async def representment(dispute_id: str, body: RepresentmentIn, db=Depends(get_db)):
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "dispute not found")
    try:
        await workflows.file_representment(
            db, d, body.statement, [e.model_dump() for e in body.evidence])
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"dispute_id": dispute_id, "state": d.state, "outcome": d.outcome}


@app.post("/api/disputes/{dispute_id}/analyst-override")
def analyst_override(dispute_id: str, body: AnalystOverrideIn, db=Depends(get_db)):
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "dispute not found")
    try:
        result = workflows.analyst_override(
            db, d, body.action, body.new_outcome, body.reason, body.analyst_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@app.post("/api/disputes/{dispute_id}/escalate")
def cardholder_escalation(dispute_id: str, body: EscalationIn, db=Depends(get_db)):
    """Cardholder contests an outcome -> escalated + feedback signal."""
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "dispute not found")
    if d.state == "resolved":
        d.state = "appealed"
    record_feedback(db, dispute_id, "cardholder_escalation",
                    {"reason": body.reason, "prior_outcome": d.outcome})
    return {"dispute_id": dispute_id, "state": d.state}


@app.post("/api/jobs/expire-windows")
async def expire_windows(db=Depends(get_db)):
    expired = await workflows.expire_merchant_windows(db)
    return {"expired": expired, "count": len(expired)}


# --------------------------------------------------------------- dashboard
@app.get("/api/dashboard/stats")
def dashboard_stats(db=Depends(get_db)):
    live = db.query(Dispute).filter(Dispute.is_historical == False)  # noqa: E712
    total = live.count()
    by_action = dict(
        db.query(Dispute.action, func.count(Dispute.id))
        .filter(Dispute.is_historical == False)  # noqa: E712
        .group_by(Dispute.action).all())
    by_state = dict(
        db.query(Dispute.state, func.count(Dispute.id))
        .filter(Dispute.is_historical == False)  # noqa: E712
        .group_by(Dispute.state).all())
    by_category = dict(
        db.query(Dispute.classified_code, func.count(Dispute.id))
        .filter(Dispute.is_historical == False)  # noqa: E712
        .group_by(Dispute.classified_code).all())
    auto = sum(v for k, v in by_action.items()
               if k in ("auto_approve", "auto_deny", "represent_chargeback"))
    decided = sum(v for k, v in by_action.items() if k)
    runs = db.query(PipelineRun).count()

    # measured prototype timing (mean of recorded run durations)
    avg_s = None
    durs = db.query(
        func.avg(func.julianday(PipelineRun.finished_at)
                 - func.julianday(PipelineRun.started_at))
    ).filter(PipelineRun.finished_at.isnot(None)).scalar()
    if durs is not None:
        avg_s = round(durs * 86400, 3)

    # today's activity (UTC)
    from datetime import datetime, timezone
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0,
                                                   second=0, microsecond=0)
    today_runs_q = db.query(PipelineRun).filter(
        PipelineRun.started_at >= day_start.replace(tzinfo=None))
    today_runs = today_runs_q.count()
    today_ids = [r.dispute_id for r in
                 today_runs_q.with_entities(PipelineRun.dispute_id).distinct()]
    today_actions = dict(
        db.query(Dispute.action, func.count(Dispute.id))
        .filter(Dispute.id.in_(today_ids)).group_by(Dispute.action).all()
    ) if today_ids else {}

    return {
        "total_disputes": total,
        "pipeline_runs": runs,
        "by_action": by_action,
        "by_state": by_state,
        "by_category": by_category,
        "auto_resolution_rate": round(auto / decided, 3) if decided else None,
        "avg_pipeline_seconds": avg_s,
        "today": {
            "runs": today_runs,
            "cases": len(today_ids),
            "auto_resolved": sum(v for k, v in today_actions.items()
                                 if k in ("auto_approve", "auto_deny")),
            "escalated": today_actions.get("escalate_to_analyst", 0),
            "evidence_requested": today_actions.get("request_more_evidence", 0),
        },
    }


@app.get("/api/dashboard/accuracy")
def dashboard_accuracy():
    return weekly_accuracy_report()


# --------------------------------------------------------------------- SSE
@app.get("/api/events/{dispute_id}")
async def dispute_events(dispute_id: str):
    """Server-sent events: live pipeline stage updates for one dispute."""
    async def stream():
        queue = bus.subscribe(dispute_id)   # history is preloaded onto the queue
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=25)
                    yield bus.sse_format(ev)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(dispute_id, queue)
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# -------------------------------------------------------------------- demo
@app.post("/api/demo/rahul")
async def demo_rahul(db=Depends(get_db)):
    """(Re-)runs the Rahul QD-01 demo case through the real pipeline."""
    d = db.query(Dispute).filter(Dispute.id == "D-DEMO-RAHUL").first()
    if not d:
        raise HTTPException(404, "Rahul demo case not seeded — run: python -m backend.db.seed")
    # reset for a fresh run
    d.state = "filed"
    d.outcome = None
    d.action = None
    d.merchant_responded = False
    db.flush()
    ctx = await orchestrator.run_pipeline(db, d, trigger="initial")
    return {"dispute_id": d.id, "record": ctx.as_record(), "state": d.state,
            "outcome": d.outcome}


@app.get("/api/demo/cases")
def demo_cases(db=Depends(get_db)):
    rows = (db.query(Dispute).filter(Dispute.id.startswith("D-DEMO"))
            .order_by(Dispute.id).all())
    return {"items": [to_dict(r) for r in rows]}
