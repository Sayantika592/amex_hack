"""Shared pipeline context passed through all 10 layers."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PipelineContext:
    """Carries the dispute and accumulated stage outputs through the pipeline.

    ``dispute`` is a plain dict snapshot of the Dispute row (so layers never
    touch the ORM session), ``stages`` maps stage-name -> stage output dict.
    """

    dispute: Dict[str, Any]
    session: Any = None                    # SQLAlchemy session (read-only use in layers)
    trigger: str = "initial"               # initial | merchant_response | representment | analyst
    stages: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    timings: Dict[str, float] = field(default_factory=dict)

    def stage(self, name: str) -> Dict[str, Any]:
        return self.stages.get(name, {})

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    def as_record(self) -> Dict[str, Any]:
        """Machine-readable record of every pipeline stage (per spec)."""
        return {
            "dispute_id": self.dispute.get("id"),
            "trigger": self.trigger,
            "elapsed_seconds": round(self.elapsed, 3),
            "timings": {k: round(v, 4) for k, v in self.timings.items()},
            "classification": self.stage("classification"),
            "graph_context_summary": _graph_summary(self.stage("graph_context")),
            "evidence_mapping": self.stage("evidence_mapping"),
            "evidence_collection": _collection_summary(self.stage("evidence_collection")),
            "evidence_scoring": _scoring_summary(self.stage("evidence_scoring")),
            "integrity": self.stage("integrity"),
            "decision": self.stage("decision"),
            "compliance": self.stage("compliance"),
            "reasoning": self.stage("reasoning"),
            "action": self.stage("action"),
            "feedback": self.stage("feedback"),
        }


def _graph_summary(g: Dict[str, Any]) -> Dict[str, Any]:
    if not g:
        return {}
    return {
        "prior_dispute_count": len(g.get("prior_disputes") or []),
        "merchant_dispute_rate": g.get("merchant_dispute_rate"),
        "merchant_loss_rate": g.get("merchant_loss_rate"),
        "device_linked_cardholders": (g.get("device") or {}).get("linked_cardholders"),
        "existing_refund": bool(g.get("existing_refund")),
        "address_familiarity_deliveries": g.get("address_familiarity_deliveries"),
        "same_product_damage_reports": g.get("same_product_damage_reports"),
        "shipment_status": (g.get("shipment") or {}).get("status"),
    }


def _collection_summary(c: Dict[str, Any]) -> Dict[str, Any]:
    if not c:
        return {}
    return {
        "dispatched_collectors": c.get("dispatched_collectors"),
        "collected_types": sorted((c.get("collected") or {}).keys()),
        "missing_required": c.get("missing_required"),
        "errors": c.get("errors"),
        "completeness": c.get("completeness"),
        "parallel_elapsed_seconds": c.get("parallel_elapsed_seconds"),
    }


def _scoring_summary(s: Dict[str, Any]) -> Dict[str, Any]:
    if not s:
        return {}
    scored = s.get("scored") or {}
    items = {}
    for k, v in scored.items():
        data = v.get("data") or {}
        item = {
            "final_strength": v.get("final_strength"),
            "strength_label": v.get("strength_label"),
            "resolved_type": v.get("resolved_type"),
            "source_party": data.get("source_party"),
            "supports": data.get("supports"),
            "notes": v.get("notes"),
        }
        img = data.get("image_analysis") or {}
        if img:
            sa = img.get("stage_a_product_verification") or {}
            dmg = img.get("damage_assessment") or {}
            item["vision"] = {
                "product_match": img.get("product_match"),
                "combined_score": sa.get("combined_score"),
                "image_similarity": sa.get("image_similarity"),
                "text_similarity": sa.get("text_similarity"),
                "has_damage": dmg.get("has_damage"),
                "severity_label": dmg.get("severity_label"),
                "damage_description": dmg.get("damage_description"),
                "model": img.get("model"),
                "mode": img.get("mode"),
            }
        items[k] = item
    return {"summary": s.get("summary"), "items": items}
