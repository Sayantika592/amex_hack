"""Layer 7 — Reasoning & Compliance Engine.

Three checks, then a grounded, human-readable explanation:
  1. Evidence assessment      — does evidence support the claim? (from Layer 6)
  2. Network rule compliance  — response windows, filing limits (config).
     A compliance override SUPERSEDES the evidence-based decision.
  3. Merchant policy compliance — did the merchant follow its own policy?

RAG: the governing rule is retrieved from config/rules_kb.yaml and cited in
every explanation.  Constrained NLG ("language model on a leash"): the rule
engine emits the exact facts; the renderer may only rephrase them into prose
via the template registry — it may not add, drop, or alter anything.  Runs on
local templates (demo mode); a hosted LLM rephraser is an optional upgrade,
never a dependency.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

import yaml

from backend.paths import CONFIG_DIR


@lru_cache(maxsize=1)
def network_rules() -> dict:
    with open(CONFIG_DIR / "network_rules.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _rules_kb() -> list[dict]:
    with open(CONFIG_DIR / "rules_kb.yaml") as f:
        return yaml.safe_load(f)["rules"]


def retrieve_rules(category: str, network: str, tags: list[str] | None = None,
                   k: int = 3) -> list[dict]:
    """Lightweight RAG retriever over the local rule KB: score by category
    match, network match, and tag keywords; return top-k with citations."""
    tags = tags or []
    scored = []
    for r in _rules_kb():
        s = 0.0
        if category in r["applies_to"]:
            s += 3.0
        if "*" in r["applies_to"]:
            s += 0.5
        if r["network"] == network:
            s += 2.0
        for t in tags:
            if t and (t.lower() in r["text"].lower() or t.lower() in r["citation"].lower()):
                s += 1.0
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [{"id": r["id"], "citation": r["citation"],
             "text": " ".join(r["text"].split()), "score": s}
            for s, r in scored[:k]]


def _dt(v):
    if v is None:
        return None
    d = datetime.fromisoformat(v) if isinstance(v, str) else v
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def check_compliance(dispute: dict, decision: dict, evidence: dict,
                     graph_context: dict, network: str) -> dict:
    rules = network_rules()["networks"][network]
    overrides, notes = [], []
    now = datetime.now(timezone.utc)

    filed = _dt(dispute.get("filed_date")) or now
    txn_ts = _dt((graph_context.get("transaction") or {}).get("timestamp"))
    notified = _dt(dispute.get("merchant_notified_date"))

    # Check 2a — merchant response window (decisive on expiry)
    if not dispute.get("merchant_responded"):
        if notified is not None:
            days = (now - notified).days
            window = rules["merchant_response_window_days"]
            if days > window and rules["auto_favor_on_no_response"]:
                overrides.append({
                    "rule": "merchant_no_response",
                    "effect": "auto_favor_cardholder",
                    "reason": f"Merchant did not respond within the {window}-day "
                              f"{network.title()} window ({days} days elapsed) — "
                              f"resolved as 'no proof provided'.",
                    "citations": retrieve_rules("*", network, ["respond", "20 days"], 1)})
            else:
                notes.append({"rule": "merchant_response_window_open",
                              "supports": "neutral",
                              "reason": f"Merchant response window open: "
                                        f"{max(rules['merchant_response_window_days'] - days, 0)}"
                                        f" of {rules['merchant_response_window_days']} days remain."})

    # Check 2b — chargeback filing time limit
    if txn_ts is not None:
        days_since_txn = (filed - txn_ts).days
        limit = rules["chargeback_time_limit_days"]
        if days_since_txn > limit:
            overrides.append({
                "rule": "past_time_limit",
                "effect": "deny_chargeback",
                "reason": f"Dispute filed {days_since_txn} days after the "
                          f"transaction (limit: {limit} days).",
                "citations": retrieve_rules("*", network, ["filing", "120"], 1)})

    # Graph override — a completed refund already made the card member whole
    refund = graph_context.get("existing_refund")
    if refund and refund.get("status") == "completed" and \
            dispute.get("user_selected_code") not in ("BA-05",):
        overrides.append({
            "rule": "refund_already_issued",
            "effect": "deny_chargeback",
            "reason": f"A completed refund of {refund['amount']} was already "
                      f"issued via {refund.get('channel', 'card')} — the dispute "
                      f"is moot (knowledge-graph relationship signal).",
            "citations": []})

    # Check 3 — merchant's own policy
    pol = graph_context.get("return_policy")
    days_since_purchase = dispute.get("days_since_purchase")
    if pol and pol.get("return_window_days") is not None and days_since_purchase is not None:
        if days_since_purchase <= pol["return_window_days"]:
            notes.append({"rule": "within_merchant_return_policy",
                          "supports": "cardholder",
                          "reason": f"Filed on day {days_since_purchase:.0f} of the "
                                    f"merchant's own {pol['return_window_days']}-day "
                                    f"policy — the merchant's policy supports the claim."})
        else:
            notes.append({"rule": "outside_merchant_return_policy",
                          "supports": "merchant",
                          "reason": f"Filed on day {days_since_purchase:.0f}, outside "
                                    f"the merchant's {pol['return_window_days']}-day policy."})
    return {"overrides": overrides, "compliance_notes": notes,
            "network": network, "checked_at": now.isoformat()}


# ------------------------------------------------------ reasoning templates
TEMPLATES: dict[str, dict[str, dict]] = {
    "delivery_proof": {
        "delivered_signed_correct_address": {
            "evidence": "Carrier tracking shows delivery to the card member's registered address with a signature on file.",
            "implication": "This is strong evidence the item was received.",
            "direction": "favors_merchant"},
        "delivered_signed_correct_address_does_not_address_condition": {
            "evidence": "Tracking shows delivery to the correct address with a signature on file.",
            "implication": "Delivery is confirmed but does not address the item's condition on arrival.",
            "direction": "favors_merchant"},
        "delivered_correct_address_no_signature": {
            "evidence": "Tracking confirms delivery to the card member's postal code, without a signature.",
            "implication": "Delivery is supported though not signature-verified.",
            "direction": "favors_merchant"},
        "delivered_correct_address_no_signature_does_not_address_condition": {
            "evidence": "Tracking confirms delivery to the correct postal code (no signature).",
            "implication": "Delivery is confirmed but says nothing about the item's condition on arrival.",
            "direction": "favors_merchant"},
        "delivered_wrong_address": {
            "evidence": "Tracking confirms delivery, but the delivery postal code does not match the card member's registered address.",
            "implication": "The package may have been delivered to the wrong location.",
            "direction": "favors_cardholder"},
        "still_in_transit": {
            "evidence": "Carrier tracking shows the shipment is still in transit.",
            "implication": "The goods have not been delivered.",
            "direction": "favors_cardholder"},
        "carrier_status_lost": {
            "evidence": "The carrier reports the shipment as lost.",
            "implication": "The goods were not delivered.",
            "direction": "favors_cardholder"},
        "carrier_status_returned": {
            "evidence": "The carrier reports the shipment was returned to sender.",
            "implication": "The goods were not delivered to the card member.",
            "direction": "favors_cardholder"},
        "no_tracking_provided": {
            "evidence": "No shipping tracking information was available for this transaction.",
            "implication": "Without tracking, the merchant cannot demonstrate the item was shipped or delivered.",
            "direction": "favors_cardholder"},
    },
    "product_condition": {
        "damage_verified_severe": {
            "evidence": "The uploaded image was verified as the disputed product. Visual analysis indicates severe damage: {detail}.",
            "implication": "The item appears unusable in its current condition.",
            "direction": "favors_cardholder"},
        "damage_verified_moderate": {
            "evidence": "The uploaded image was verified as the disputed product. Visual analysis indicates moderate damage: {detail}.",
            "implication": "The item's condition is materially impaired.",
            "direction": "favors_cardholder"},
        "damage_verified_minor": {
            "evidence": "The uploaded image was verified as the disputed product with minor cosmetic damage: {detail}.",
            "implication": "The impairment appears cosmetic; a partial credit may be appropriate.",
            "direction": "favors_cardholder"},
        "no_damage_visible": {
            "evidence": "The uploaded image was verified as the correct product, but no visible damage was detected.",
            "implication": "Visual evidence does not support the damage claim.",
            "direction": "favors_merchant"},
        "image_product_mismatch": {
            "evidence": "The uploaded photo could not be verified as the disputed product (similarity below threshold).",
            "implication": "The photographic evidence cannot support the claim.",
            "direction": "favors_merchant"},
        "cardholder_statement_only": {
            "evidence": "The card member provided a written description of the condition issue without verifiable imagery.",
            "implication": "The statement is supportive but not independently verifiable.",
            "direction": "favors_cardholder"},
    },
    "transaction_pattern": {
        "duplicate_within_5_min": {
            "evidence": "A matching charge of the same amount to the same merchant was found {detail}.",
            "implication": "The timing strongly suggests a duplicate charge rather than two separate purchases.",
            "direction": "favors_cardholder"},
        "similar_charge_within_24h": {
            "evidence": "A charge of the same amount to the same merchant occurred within 24 hours ({detail}).",
            "implication": "The pattern is consistent with a possible duplicate.",
            "direction": "favors_cardholder"},
        "no_duplicate_pattern": {
            "evidence": "No duplicate or similar charges were detected in the transaction history.",
            "implication": "Transaction patterns do not support a duplicate-charge claim.",
            "direction": "favors_merchant"},
        "charge_exceeds_authorization": {
            "evidence": "The settled amount exceeds the authorization on record ({detail}).",
            "implication": "The excess was not authorized by the card member.",
            "direction": "favors_cardholder"},
        "charge_matches_authorization": {
            "evidence": "The settled amount matches the authorization on record.",
            "implication": "The charged amount was authorized.",
            "direction": "favors_merchant"},
        "atm_short_dispense": {
            "evidence": "ATM terminal logs show less cash dispensed than the amount debited.",
            "implication": "The card member did not receive the full withdrawal.",
            "direction": "favors_cardholder"},
        "atm_full_dispense_logged": {
            "evidence": "ATM terminal logs record a complete dispense of the debited amount.",
            "implication": "The terminal balanced for this withdrawal.",
            "direction": "favors_merchant"},
    },
    "merchant_documentation": {
        "merchant_docs_present": {
            "evidence": "The merchant supplied supporting documentation ({detail}).",
            "implication": "The merchant's records substantiate its position.",
            "direction": "favors_merchant"},
        "merchant_docs_absent_burden_unmet": {
            "evidence": "The merchant provided no documentation discharging its burden of proof.",
            "implication": "Absent such proof, the outcome defaults toward the card member.",
            "direction": "favors_cardholder"},
        "merchant_docs_absent": {
            "evidence": "No merchant documentation was available for this case.",
            "implication": "The merchant's position is not documented.",
            "direction": "favors_cardholder"},
    },
    "cardholder_documentation": {
        "cardholder_docs_present": {
            "evidence": "The card member supplied supporting documentation ({detail}).",
            "implication": "The claim is documented from the card member's side.",
            "direction": "favors_cardholder"},
        "cardholder_docs_absent_burden_unmet": {
            "evidence": "The card member provided no documentation for a claim where the burden rests with the filer.",
            "implication": "Absent such proof, the outcome defaults toward the merchant.",
            "direction": "favors_merchant"},
        "cardholder_docs_absent": {
            "evidence": "No card member documentation was provided.",
            "implication": "The claim rests on the system-gathered evidence alone.",
            "direction": "neutral"},
    },
    "communication_records": {
        "cancellation_confirmed_before_charge": {
            "evidence": "A cancellation confirmation predating the charge is on record ({detail}).",
            "implication": "Billing after a confirmed cancellation is the merchant's liability.",
            "direction": "favors_cardholder"},
        "cancellation_after_charge": {
            "evidence": "The cancellation on record postdates the disputed charge.",
            "implication": "The charge preceded the cancellation.",
            "direction": "favors_merchant"},
        "merchant_promised_refund_in_writing": {
            "evidence": "The merchant promised a refund in writing.",
            "implication": "A promised credit that was never processed supports the claim.",
            "direction": "favors_cardholder"},
        "communications_support_cardholder": {
            "evidence": "The communication thread corroborates the card member's account.",
            "implication": "Contemporaneous messages support the claim.",
            "direction": "favors_cardholder"},
        "communications_support_merchant": {
            "evidence": "The communication thread corroborates the merchant's account.",
            "implication": "Contemporaneous messages support the merchant.",
            "direction": "favors_merchant"},
        "communications_neutral": {
            "evidence": "Communications between the parties are inconclusive.",
            "implication": "The thread does not favour either side.",
            "direction": "neutral"},
        "no_communication_records": {
            "evidence": "No communication records were found between the parties.",
            "implication": "No corroborating correspondence exists.",
            "direction": "neutral"},
    },
    "historical_pattern": {
        "_default": {
            "evidence": "Relationship history: {reason}.",
            "implication": "History is a capped, symmetric tie-breaker and never decides a case.",
            "direction": "neutral"},
        "no_material_history": {
            "evidence": "Neither party's history materially affects this case.",
            "implication": "The decision rests on the case evidence.",
            "direction": "neutral"},
    },
    "policy_compliance": {
        "within_merchant_policy_window": {
            "evidence": "The claim falls within the merchant's own policy window ({detail}).",
            "implication": "The merchant's own terms support the card member.",
            "direction": "favors_cardholder"},
        "outside_merchant_policy_window": {
            "evidence": "The claim falls outside the merchant's disclosed policy window ({detail}).",
            "implication": "The merchant's disclosed terms support the merchant.",
            "direction": "favors_merchant"},
        "policy_terms_not_disclosed": {
            "evidence": "The relevant terms were not properly disclosed at purchase.",
            "implication": "Undisclosed terms cannot be enforced against the card member.",
            "direction": "favors_cardholder"},
        "policy_terms_disclosed": {
            "evidence": "The relevant terms were disclosed at purchase.",
            "implication": "Disclosed terms bind the transaction.",
            "direction": "favors_merchant"},
        "no_policy_on_file": {
            "evidence": "No applicable merchant policy is on file.",
            "implication": "Policy terms do not affect this case.",
            "direction": "neutral"},
        "policy_neutral": {
            "evidence": "The applicable policy does not determine this case.",
            "implication": "Policy terms are neutral here.",
            "direction": "neutral"},
    },
    "digital_access_logs": {
        "access_logs_show_usage": {
            "evidence": "Platform logs show the digital goods were delivered and accessed ({detail}).",
            "implication": "Delivery of the digital goods is demonstrated.",
            "direction": "favors_merchant"},
        "logs_show_no_access_or_delivery": {
            "evidence": "Platform logs show no delivery or access of the digital goods.",
            "implication": "Delivery of the digital goods is not demonstrated.",
            "direction": "favors_cardholder"},
        "no_access_logs_burden_unmet": {
            "evidence": "No delivery or access logs were produced for the digital goods.",
            "implication": "Without logs, the merchant cannot demonstrate provisioning.",
            "direction": "favors_cardholder"},
        "digital_logs_not_material": {
            "evidence": "Digital access logs are not material to this category.",
            "implication": "This dimension does not affect the outcome.",
            "direction": "neutral"},
    },
    "image_visual_analysis": {
        "visual_damage_severe": {
            "evidence": "Two-stage image analysis (product verification, then damage assessment) confirms severe damage: {detail}.",
            "implication": "The visual evidence strongly supports the claim.",
            "direction": "favors_cardholder"},
        "visual_damage_moderate": {
            "evidence": "Two-stage image analysis confirms moderate damage: {detail}.",
            "implication": "The visual evidence supports the claim.",
            "direction": "favors_cardholder"},
        "visual_damage_minor": {
            "evidence": "Two-stage image analysis confirms minor cosmetic damage: {detail}.",
            "implication": "The visual evidence supports a partial remedy.",
            "direction": "favors_cardholder"},
        "image_verified_no_damage": {
            "evidence": "The image was verified as the product; no damage was detected.",
            "implication": "The visual evidence does not support the claim.",
            "direction": "favors_merchant"},
        "image_product_mismatch": {
            "evidence": "Stage A verification flagged a possible product mismatch ({detail}).",
            "implication": "The photo cannot be relied on as evidence of this product.",
            "direction": "favors_merchant"},
        "image_verified_product": {
            "evidence": "The uploaded image was verified as the disputed product.",
            "implication": "The photographic evidence is authentic to the case.",
            "direction": "neutral"},
        "no_image_evidence": {
            "evidence": "No image evidence was uploaded.",
            "implication": "Visual analysis is unavailable for this case.",
            "direction": "neutral"},
    },
}


def _template_for(dimension: str, reason: str) -> dict | None:
    bank = TEMPLATES.get(dimension, {})
    if reason in bank:
        return bank[reason]
    for key, t in bank.items():
        if key != "_default" and reason.startswith(key):
            return t
    return bank.get("_default")


def generate_explanation(decision: dict, compliance: dict, action: dict,
                         network: str) -> dict:
    """Constrained NLG: assembles prose STRICTLY from the emitted facts and the
    template registry. Nothing is added, dropped, or altered."""
    factors = decision["factor_breakdown"]
    order = sorted(factors.items(), key=lambda kv: abs(kv[1]["weighted"]),
                   reverse=True)
    citations = retrieve_rules(decision["category"], network, k=2)
    statements = []
    for dimension, f in order:
        t = _template_for(dimension, f["reason"])
        if t is None or f["direction_score"] == 0 and f["reason"].startswith("no_"):
            continue
        text = t["evidence"].format(detail=f.get("detail", ""),
                                    reason=f.get("reason", "")).replace("  ", " ")
        statements.append({
            "dimension": dimension,
            "weight": f["weight"],
            "contribution": f["weighted"],
            "evidence_strength": f["evidence_strength"],
            "text": text,
            "implication": t["implication"],
            "direction": t["direction"],
        })
    decision_text = {
        "favor_cardholder": "Resolved in favour of the Card Member.",
        "favor_merchant": "Resolved in favour of the Merchant.",
        "escalate": "This case has been escalated for manual review.",
        "inconclusive": "More information is required before a decision.",
    }.get(action["outcome"], action["outcome"])
    burden = decision["burden_of_proof"]
    summary_bits = [s["text"] for s in statements[:3]]
    for o in compliance["overrides"]:
        summary_bits.insert(0, o["reason"])
    return {
        "decision_statement": decision_text,
        "confidence_pct": f"{int(action.get('confidence', 0) * 100)}%",
        "burden_of_proof": {
            "bearer": burden["bearer"],
            "requirement": burden["requirement"],
            "default_if_not_met": burden["default_outcome"],
        },
        "summary": " ".join(summary_bits),
        "detailed_factors": statements,
        "rule_citations": citations + [c for o in compliance["overrides"]
                                       for c in o.get("citations", [])],
        "compliance_notes": compliance["compliance_notes"],
        "overrides_applied": compliance["overrides"],
        "nlg": {"engine": "constrained template assembly (rule-engine facts only)",
                "mode": "demo",
                "note": "A hosted LLM rephraser is an optional upgrade, never a "
                        "dependency; every sentence traces to an emitted fact."},
    }


def run(ctx) -> dict:
    decision = ctx.stages["decision"]
    compliance = check_compliance(ctx.dispute, decision,
                                  ctx.stages["evidence_collection"],
                                  ctx.stages["graph_context"],
                                  ctx.dispute["network"])
    return compliance
