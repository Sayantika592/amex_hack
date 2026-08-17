"""Layer 3 — Dynamic Evidence Collection Engine.

Receives the exact evidence-type list from Layer 2 and dispatches ONLY those
collectors, in parallel (asyncio.gather).  Each collector is a self-contained
module that knows how to fetch one evidence type; in this environment
collectors read the operational store (which stands in for the carrier /
gateway / merchant APIs a production deployment would call).  `missing_required`
feeds Layer 8 — the recommendation may be "request more evidence" instead of
deciding on incomplete information.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from backend.db import models as m
from backend.db.database import SessionLocal
from backend.vision.adapters import get_vision


def _payloads(db, dispute_id: str, evidence_type: str) -> list[dict]:
    rows = (db.query(m.EvidenceItem)
              .filter_by(dispute_id=dispute_id, evidence_type=evidence_type).all())
    return [{"payload": r.payload or {}, "source_party": r.source_party,
             "dated": r.dated, "age_days": r.age_days} for r in rows]


def _first(db, dispute_id, evidence_type):
    rows = _payloads(db, dispute_id, evidence_type)
    return rows[0] if rows else None


async def _generic_collector(evidence_type, dispute, graph_context):
    """Default collector: pulls the stored evidence item of this type."""
    with SessionLocal() as db:
        row = _first(db, dispute["id"], evidence_type)
    if row is None:
        return {"status": "not_available", "evidence_strength_hint": "none"}
    return {"status": "collected", **row["payload"],
            "source_party": row["source_party"], "dated": row["dated"],
            "age_days": row["age_days"]}


async def fetch_shipping_tracking(evidence_type, dispute, graph_context):
    """Carrier API stand-in (FedEx/UPS/USPS/DHL/BlueDart in production)."""
    shp = graph_context.get("shipment")
    if not shp or not shp.get("tracking_number"):
        return {"status": "no_tracking_provided"}
    ch_zip = (graph_context.get("cardholder") or {}).get("billing_zip")
    return {
        "status": "collected",
        "tracking_number": shp["tracking_number"],
        "carrier": shp["carrier"],
        "delivery_status": shp["status"],
        "delivered_at": shp.get("delivery_date"),
        "delivered_to_zip": shp.get("delivery_zip"),
        "cardholder_zip": ch_zip,
        "zip_match": (shp.get("delivery_zip") == ch_zip
                      if shp.get("delivery_zip") and ch_zip else None),
        "signature_on_file": bool(shp.get("signature_on_file")),
    }


async def fetch_delivery_confirmation(evidence_type, dispute, graph_context):
    shp = graph_context.get("shipment")
    if not shp:
        return {"status": "not_available"}
    if shp["status"] != "delivered":
        return {"status": "collected", "delivered": False,
                "carrier_status": shp["status"]}
    return {"status": "collected", "delivered": True,
            "delivered_at": shp.get("delivery_date"),
            "signature_on_file": bool(shp.get("signature_on_file")),
            "delivery_zip": shp.get("delivery_zip"),
            "familiar_address_deliveries":
                graph_context.get("address_familiarity_deliveries", 0)}


async def fetch_address_verification(evidence_type, dispute, graph_context):
    ch = graph_context.get("cardholder") or {}
    shp = graph_context.get("shipment") or {}
    return {"status": "collected", "billing_zip": ch.get("billing_zip"),
            "shipping_zip": shp.get("delivery_zip"),
            "zip_match": (shp.get("delivery_zip") == ch.get("billing_zip")
                          if shp.get("delivery_zip") and ch.get("billing_zip") else None)}


async def fetch_related_transactions(evidence_type, dispute, graph_context):
    """All transactions at the same merchant within +/-7 days (duplicate scan)."""
    from datetime import timedelta
    txn = graph_context.get("transaction")
    if not txn:
        return {"status": "not_available"}
    t0 = datetime.fromisoformat(txn["timestamp"])
    with SessionLocal() as db:
        rows = (db.query(m.Transaction)
                  .filter(m.Transaction.merchant_id == dispute["merchant_id"],
                          m.Transaction.card_member_id == dispute["card_member_id"],
                          m.Transaction.timestamp >= t0 - timedelta(days=7),
                          m.Transaction.timestamp <= t0 + timedelta(days=7))
                  .all())
    return {"status": "collected", "disputed_transaction": txn,
            "transactions": [{"id": r.id, "amount": r.amount,
                              "merchant_id": r.merchant_id,
                              "timestamp": r.timestamp.isoformat()} for r in rows]}


async def fetch_refund_records(evidence_type, dispute, graph_context):
    with SessionLocal() as db:
        rows = (db.query(m.Refund)
                  .filter_by(transaction_id=dispute["transaction_id"]).all())
    if not rows:
        return {"status": "collected", "refunds": [], "refund_found": False}
    return {"status": "collected", "refund_found": True,
            "refunds": [{"id": r.id, "amount": r.amount, "status": r.status,
                         "channel": r.channel,
                         "completed": r.status == "completed"} for r in rows]}


async def fetch_return_policy(evidence_type, dispute, graph_context):
    pol = graph_context.get("return_policy")
    if not pol:
        with SessionLocal() as db:
            row = (db.query(m.Policy)
                     .filter_by(merchant_id=dispute["merchant_id"]).first())
        if not row:
            return {"status": "not_available"}
        pol = {"return_window_days": row.return_window_days, "terms": row.terms}
    return {"status": "collected", **pol}


async def fetch_cardholder_photos(evidence_type, dispute, graph_context):
    """Runs the two-stage image pipeline (Stage A CLIP verification,
    Stage B BLIP-2 damage VQA — or DeterministicVision in demo mode)."""
    with SessionLocal() as db:
        photo = _first(db, dispute["id"], "cardholder_photos")
        listing = _first(db, dispute["id"], "product_listing")
    if photo is None:
        return {"status": "not_available"}
    vision = get_vision()
    product_type = (listing or {}).get("payload", {}).get("category", "product")
    analysis = vision.analyze(photo["payload"], (listing or {}).get("payload", {}),
                              product_type)
    return {"status": "collected", "image_ref": photo["payload"].get("image_ref"),
            "dated": photo["dated"], "image_analysis": analysis,
            "ai_verified_product_match": analysis["product_match"]}


COLLECTOR_REGISTRY = {
    "shipping_tracking": fetch_shipping_tracking,
    "delivery_confirmation": fetch_delivery_confirmation,
    "cardholder_address_verification": fetch_address_verification,
    "all_transactions_same_merchant_7d": fetch_related_transactions,
    "related_transactions": fetch_related_transactions,
    "refund_records": fetch_refund_records,
    "merchant_return_policy": fetch_return_policy,
    "cardholder_photos": fetch_cardholder_photos,
    # every other evidence type resolves through the generic store collector
}


class DynamicEvidenceCollector:
    """Collects ONLY what the Evidence Mapping Matrix specifies, in parallel."""

    async def collect(self, requirements: dict, dispute: dict,
                      graph_context: dict) -> dict:
        plan = list(requirements["union_required"]) + list(requirements["union_optional"])
        started = datetime.now(timezone.utc)
        tasks, names = [], []
        for evidence_type in plan:
            collector = COLLECTOR_REGISTRY.get(evidence_type, _generic_collector)
            tasks.append(collector(evidence_type, dispute, graph_context))
            names.append(evidence_type)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        collected, errors = {}, []
        for name, result in zip(names, results):
            if isinstance(result, Exception):
                errors.append({"evidence_type": name, "error": str(result)})
            elif result.get("status") in ("not_available", "no_tracking_provided"):
                collected[name] = result   # keep the negative signal — it is evidence
            else:
                collected[name] = result

        available = {k for k, v in collected.items()
                     if v.get("status") == "collected"}
        missing = [e for e in requirements["union_required"] if e not in available]
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        return {
            "collected": collected,
            "dispatched_collectors": names,
            "missing_required": missing,
            "errors": errors,
            "completeness": round(len(available) / max(len(plan), 1), 3),
            "parallel_elapsed_seconds": round(elapsed, 4),
        }


async def run(ctx) -> dict:
    collector = DynamicEvidenceCollector()
    return await collector.collect(
        ctx.stages["evidence_mapping"], ctx.dispute, ctx.stages["graph_context"])


def run_sync(ctx) -> dict:
    """Standalone/script use only (no running event loop)."""
    return asyncio.run(run(ctx))
