"""Layer 5 — Dispute Integrity Engine (ADVISORY ONLY).

A genuine customer can have weak evidence; a fraudster can have convincing
evidence — so integrity is completely separate from evidence quality (Layer 4).
The engine evaluates whether the DISPUTE ITSELF looks like friendly fraud or
first-party misuse using behavioural knowledge-graph signals.  It flags; it
NEVER auto-denies.  Flagged cases go to a human analyst (Layer 8 enforces).
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

import yaml

from backend.paths import CONFIG_DIR


@lru_cache(maxsize=1)
def _rules() -> dict:
    with open(CONFIG_DIR / "integrity_rules.yaml") as f:
        return yaml.safe_load(f)


def _hours_since_purchase(dispute: dict, graph_context: dict) -> float | None:
    txn = graph_context.get("transaction")
    if not txn or not txn.get("timestamp") or not dispute.get("filed_date"):
        return None
    t = datetime.fromisoformat(txn["timestamp"])
    f = datetime.fromisoformat(dispute["filed_date"])
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    if f.tzinfo is None:
        f = f.replace(tzinfo=timezone.utc)
    return (f - t).total_seconds() / 3600.0


def compute_suspicion_score(dispute: dict, graph_context: dict,
                            scored_evidence: dict) -> dict:
    r = _rules()["signals"]
    signals = []

    prior = graph_context.get("prior_disputes", [])
    if len(prior) > r["high_dispute_frequency"]["threshold_prior_disputes"]:
        signals.append({
            "signal": "high_dispute_frequency",
            "score": min(len(prior) / r["high_dispute_frequency"]["score_divisor"],
                         r["high_dispute_frequency"]["max_score"]),
            "detail": f"{len(prior)} prior disputes on file"})

    hours = _hours_since_purchase(dispute, graph_context)
    if hours is not None and 0 <= hours < r["very_early_dispute"]["threshold_hours"]:
        signals.append({"signal": "very_early_dispute",
                        "score": r["very_early_dispute"]["score"],
                        "detail": f"Disputed {hours:.1f}h after purchase"})

    device = graph_context.get("device") or {}
    if device.get("linked_cardholders", 1) > r["shared_device"]["threshold_accounts"]:
        signals.append({"signal": "shared_device",
                        "score": r["shared_device"]["score"],
                        "detail": f"Device linked to "
                                  f"{device['linked_cardholders']} card member accounts"})

    rate = graph_context.get("merchant_dispute_rate", 0.0)
    if 0 < rate < r["low_risk_merchant"]["threshold_dispute_rate"]:
        signals.append({"signal": "low_risk_merchant",
                        "score": r["low_risk_merchant"]["score"],
                        "detail": "Merchant dispute rate is exceptionally low"})

    same_cat = graph_context.get("prior_same_macro_category", 0)
    if same_cat >= r["serial_same_category"]["threshold_same_category"]:
        signals.append({"signal": "serial_same_category",
                        "score": r["serial_same_category"]["score"],
                        "detail": f"{same_cat} prior disputes in the same "
                                  f"category across merchants"})

    resolved_prior = [p for p in prior if p.get("outcome")]
    if len(resolved_prior) >= r["high_loss_rate_filer"]["threshold_prior"]:
        losses = sum(1 for p in resolved_prior if p["outcome"] == "favor_merchant")
        loss_rate = losses / len(resolved_prior)
        if loss_rate >= r["high_loss_rate_filer"]["threshold_loss_rate"]:
            signals.append({"signal": "high_loss_rate_filer",
                            "score": r["high_loss_rate_filer"]["score"],
                            "detail": f"{losses}/{len(resolved_prior)} prior "
                                      f"disputes resolved against the filer"})

    cap = _rules()["cap"]
    suspicion = min(sum(s["score"] for s in signals) / len(signals), cap) if signals else 0.0
    flag = _flag_threshold()
    return {
        "suspicion_score": round(suspicion, 3),
        "signals": signals,
        "is_suspicious": suspicion > flag,
        "action": "flag_for_review" if suspicion > flag else "proceed_normally",
        "advisory_only": True,
        "note": "Integrity is advisory only — flags route to a human analyst; "
                "the engine never auto-denies.",
    }


@lru_cache(maxsize=1)
def _flag_threshold() -> float:
    with open(CONFIG_DIR / "decision_thresholds.yaml") as f:
        return yaml.safe_load(f)["integrity"]["suspicion_flag"]


def run(ctx) -> dict:
    return compute_suspicion_score(ctx.dispute, ctx.stages["graph_context"],
                                   ctx.stages["evidence_scoring"])
