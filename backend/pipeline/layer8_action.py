"""Layer 8 — Action Recommendation Engine.

Five business actions (not binary approve/reject):
  auto_approve | auto_deny | request_more_evidence | represent_chargeback |
  escalate_to_analyst

Cost-asymmetric decisioning: denying a genuine victim is the costlier error,
so uncertainty escalates or leans toward the card member; auto_deny requires
clear evidence.  The Dispute Integrity flag NEVER auto-denies — it escalates.
Order of evaluation:
  1. compliance overrides   (network rules supersede evidence)
  2. multi-category conflict hold (clarification needed)
  3. integrity flag         (advisory -> human analyst)
  4. missing evidence       (request more before deciding)
  5. score bands            (config/decision_thresholds.yaml)
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from backend.paths import CONFIG_DIR


@lru_cache(maxsize=1)
def thresholds() -> dict:
    with open(CONFIG_DIR / "decision_thresholds.yaml") as f:
        return yaml.safe_load(f)


def _refund_amount(dispute: dict, decision: dict, evidence: dict,
                   override: bool = False) -> tuple[float, str]:
    """Partial-refund support (edge cases §15): proportional for partial
    receipt; 15-30% credit for minor cosmetic damage; full otherwise.
    Compliance overrides always refund in full: 'no proof provided' means
    the merchant's own records cannot be used to prorate the refund."""
    amount = float(dispute.get("amount") or 0.0)
    if override:
        return amount, "full refund (network-rule override — merchant records " \
                       "cannot prorate an undischarged burden)"
    category = decision["category"]
    factors = decision["factor_breakdown"]

    if category == "NR-02":
        ff = (evidence["collected"].get("merchant_fulfillment_status") or {})
        ordered = ff.get("items_ordered")
        delivered = ff.get("items_delivered")
        if ordered and delivered is not None and ordered > 0:
            missing_frac = max(ordered - delivered, 0) / ordered
            return round(amount * missing_frac, 2), \
                f"proportional refund for {ordered - delivered} of {ordered} items missing"
        return round(amount * 0.5, 2), "proportional refund (missing-item share unverified, 50%)"

    cond = factors.get("product_condition", {})
    if category == "QD-01" and cond.get("reason") == "damage_verified_minor":
        return round(amount * 0.25, 2), "25% credit for minor cosmetic damage"
    return amount, "full refund"


def recommend_action(decision: dict, integrity: dict, compliance: dict,
                     evidence: dict, dispute: dict) -> dict:
    th = thresholds()
    bands = th["score_bands"]
    score = decision.get("composite_score", decision["final_score"])
    suspicion = integrity["suspicion_score"]
    overrides = compliance.get("overrides", [])
    completeness = evidence.get("completeness", 1.0)
    missing = evidence.get("missing_required", [])

    def result(action, outcome, reason, **extra):
        out = {"action": action, "outcome": outcome, "reason": reason,
               "final_score": score, "confidence": round(min(abs(score) + 0.4, 0.98), 2)
               if action in ("auto_approve", "auto_deny", "represent_chargeback")
               else round(max(1 - abs(score), 0.3), 2),
               "cost_asymmetry_note": "Uncertain cases escalate or lean toward "
                                      "the card member; auto-deny requires clear evidence."}
        out.update(extra)
        if action == "auto_approve":
            refund, refund_note = _refund_amount(
                dispute, decision, evidence,
                override=(reason == "compliance_override"))
            out["refund_amount"] = refund
            out["refund_note"] = refund_note
            out["currency"] = dispute.get("currency", "INR")
        return out

    # 1. compliance overrides supersede evidence
    for o in overrides:
        if o["effect"] == "auto_favor_cardholder":
            return result("auto_approve", "favor_cardholder",
                          "compliance_override", detail=o["reason"],
                          override_rule=o["rule"])
        if o["effect"] == "deny_chargeback":
            return result("auto_deny", "favor_merchant",
                          "compliance_override", detail=o["reason"],
                          override_rule=o["rule"])

    # 2. multi-category logical conflict -> clarification, never auto-resolve
    if decision.get("conflict_hold"):
        return result("request_more_evidence", "inconclusive",
                      "conflicting_sub_claims",
                      detail="; ".join(c["conflict"] for c in decision["conflicts"]),
                      requested_from="cardholder",
                      requested_items=["clarify_conflicting_claims"])

    # 3. integrity flag — advisory only, routes to a human, NEVER auto-denies
    if suspicion > th["integrity"]["suspicion_flag"]:
        return result("escalate_to_analyst", "escalate",
                      "integrity_signals_detected",
                      suspicion_score=suspicion,
                      signals=integrity["signals"])

    # 4. incomplete evidence -> request more before deciding
    #    (unless a conclusive fact already decides the case — remaining
    #    evidence cannot overturn a verified duplicate/cancellation/etc.)
    conclusive = decision.get("conclusive_evidence") or []
    if (completeness < th["evidence"]["min_completeness"] and missing
            and not conclusive):
        return result("request_more_evidence", "inconclusive",
                      "insufficient_evidence",
                      missing_required=missing,
                      requested_from="merchant"
                      if any(m in ("qc_records", "pre_shipment_inspection",
                                   "authorization_log", "refund_records")
                             for m in missing) else "both")

    # 5. score bands
    if score >= bands["favor_cardholder_high"]:
        return result("auto_approve", "favor_cardholder",
                      "strong_evidence_for_cardholder")
    if score >= bands["favor_cardholder"]:
        return result("auto_approve", "favor_cardholder",
                      "evidence_favors_cardholder",
                      escalation_option="Merchant may contest via representment.")
    if score > bands["escalation_low"]:
        return result("escalate_to_analyst", "escalate",
                      "evidence_inconclusive_human_review",
                      detail=f"Score {score:+.2f} in the -0.3..+0.3 escalation zone; "
                             f"the system is decisive only when evidence is clear.")
    if score > bands["favor_merchant"]:
        return result("represent_chargeback", "favor_merchant",
                      "evidence_favors_merchant",
                      detail="Representment package pre-filled for the merchant; "
                             "card member retains an easy escalation option.")
    return result("auto_deny", "favor_merchant", "strong_evidence_for_merchant",
                  escalation_option="Card member may escalate to an analyst.")


def run(ctx) -> dict:
    return recommend_action(ctx.stages["decision"], ctx.stages["integrity"],
                            ctx.stages["compliance"],
                            ctx.stages["evidence_collection"], ctx.dispute)
