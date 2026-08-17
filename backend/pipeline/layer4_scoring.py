"""Layer 4 — Evidence Strength Scoring.

Every piece of evidence is scored INDEPENDENTLY before the decision model
sees it:  final = base_strength x quality_modifier x recency_modifier,
labelled strong (>=0.8) / moderate (>=0.5) / weak (>=0.2) / none.
Deterministic, auditable, configured in config/evidence_strength.yaml.
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from backend.paths import CONFIG_DIR


@lru_cache(maxsize=1)
def _cfg() -> dict:
    with open(CONFIG_DIR / "evidence_strength.yaml") as f:
        return yaml.safe_load(f)


def strength_label(v: float) -> str:
    labels = _cfg()["labels"]
    if v >= labels["strong"]:
        return "strong"
    if v >= labels["moderate"]:
        return "moderate"
    if v >= labels["weak"]:
        return "weak"
    return "none"


def assess_quality(etype: str, data: dict) -> tuple[float, list[str]]:
    q = _cfg()["quality_modifiers"]
    mod, notes = 1.0, []
    if etype in ("shipping_tracking", "delivery_confirmation",
                 "cardholder_address_verification"):
        zm = data.get("zip_match")
        if zm is True:
            mod *= q["zip_match_bonus"]; notes.append("delivery zip matches billing zip")
        elif zm is False:
            mod *= q["zip_mismatch_penalty"]; notes.append("delivery zip does NOT match")
    if etype in ("cardholder_photos", "packaging_photos"):
        if data.get("ai_verified_product_match") is True:
            mod *= q["ai_verified_photo_bonus"]; notes.append("AI-verified as the disputed product")
        elif data.get("ai_verified_product_match") is False:
            mod *= q["ai_unverified_photo_penalty"]; notes.append("possible product mismatch flagged")
    if data.get("dated") is False:
        mod *= q["undated_penalty"]; notes.append("undated evidence")
    return mod, notes


def assess_recency(data: dict) -> tuple[float, str]:
    r = _cfg()["recency"]
    age = data.get("age_days")
    if age is None:
        return r["fresh_modifier"], "recency unknown"
    if age <= r["fresh_days"]:
        return r["fresh_modifier"], f"fresh ({age:.0f}d)"
    if age <= r["stale_days"]:
        return r["stale_modifier"], f"aging ({age:.0f}d)"
    return r["very_stale_modifier"], f"stale ({age:.0f}d)"


def _base_for(etype: str, data: dict) -> tuple[str, float]:
    """Some collectors resolve to a more specific strength key."""
    base = _cfg()["base_strength"]
    if etype == "shipping_tracking":
        st = data.get("delivery_status")
        if st == "delivered" and data.get("signature_on_file"):
            return "signed_proof_of_delivery", base["signed_proof_of_delivery"]
        if st == "delivered":
            return "carrier_tracking_delivered", base["carrier_tracking_delivered"]
        if st == "in_transit":
            return "carrier_tracking_in_transit", base["carrier_tracking_in_transit"]
        return "shipping_tracking", base["shipping_tracking"] * 0.5
    if etype == "cardholder_photos" and data.get("image_analysis"):
        return "ai_damage_assessment", base["ai_damage_assessment"]
    return etype, base.get(etype, 0.30)


def score_evidence(evidence_bundle: dict) -> dict:
    scored = {}
    for etype, data in evidence_bundle["collected"].items():
        if data.get("status") in ("not_available", "no_tracking_provided"):
            scored[etype] = {
                "data": data, "base_strength": 0.0, "quality_modifier": 1.0,
                "recency_modifier": 1.0, "final_strength": 0.0,
                "strength_label": "none",
                "resolved_type": etype,
                "notes": ["evidence not provided / not available"],
            }
            continue
        resolved, base_strength = _base_for(etype, data)
        qmod, qnotes = assess_quality(etype, data)
        rmod, rnote = assess_recency(data)
        final = min(base_strength * qmod * rmod, 1.0)
        scored[etype] = {
            "data": data,
            "base_strength": round(base_strength, 3),
            "quality_modifier": round(qmod, 3),
            "recency_modifier": round(rmod, 3),
            "final_strength": round(final, 3),
            "strength_label": strength_label(final),
            "resolved_type": resolved,
            "notes": qnotes + [rnote],
        }
    summary = {
        "strong": sum(1 for s in scored.values() if s["strength_label"] == "strong"),
        "moderate": sum(1 for s in scored.values() if s["strength_label"] == "moderate"),
        "weak": sum(1 for s in scored.values() if s["strength_label"] == "weak"),
        "none": sum(1 for s in scored.values() if s["strength_label"] == "none"),
    }
    return {"scored": scored, "summary": summary}


def run(ctx) -> dict:
    return score_evidence(ctx.stages["evidence_collection"])
