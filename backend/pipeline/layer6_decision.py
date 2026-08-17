"""Layer 6 — Fair-Weighing Decision Model.

Receives PRE-SCORED evidence (Layer 4) and applies CATEGORY-SPECIFIC weights
(config/weights.yaml, materialized from the Excel 'Evidence Weight matrix'
sheet — authoritative).  Output: directional score in [-1, +1]
(-1 favours merchant, +1 favours card member) with a full factor breakdown.

Fairness safeguards implemented here:
  * Demographic blindness — scorers never receive name, age, gender,
    ethnicity, card tier, or merchant size (see _blind()).
  * Merchant history is symmetric and capped (~10% profile weight); it breaks
    near-ties only and never decides a case.
  * Multi-category disputes decompose into independent sub-decisions; logical
    contradictions between sub-claims pause auto-resolution.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

import yaml

from backend.paths import CONFIG_DIR

# ------------------------------------------------------------- weight config
@lru_cache(maxsize=1)
def weight_config() -> dict:
    with open(CONFIG_DIR / "weights.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _thresholds() -> dict:
    with open(CONFIG_DIR / "decision_thresholds.yaml") as f:
        return yaml.safe_load(f)


def weights_for(category: str) -> tuple[str, dict]:
    cfg = weight_config()
    profile = cfg["profile_map"].get(category, "QD")
    return profile, cfg["profiles"][profile]


BLINDED_FIELDS = {"name", "age", "gender", "ethnicity", "card_tier", "size",
                  "demographic_note", "tenure_years"}


def _blind(obj: dict | None) -> dict:
    """Demographic blindness: strip identity attributes before scoring."""
    if not obj:
        return {}
    return {k: v for k, v in obj.items() if k not in BLINDED_FIELDS}


# ------------------------------------------------------------ dimension scorers
# Convention: +1.0 favours the card member, -1.0 favours the merchant.
# Each returns {score, reason, evidence_strength, detail}.

def _ev(scored: dict, *names):
    for n in names:
        item = scored.get(n)
        if item and item["strength_label"] != "none":
            return item
    return None


def score_delivery_proof(scored, graph, category, dispute):
    item = _ev(scored, "shipping_tracking", "delivery_confirmation")
    if item is None:
        # burden usually on merchant for NR: no tracking cannot demonstrate delivery
        if category.startswith("NR"):
            return {"score": 0.7, "reason": "no_tracking_provided",
                    "evidence_strength": "none"}
        return {"score": 0.0, "reason": "delivery_not_material",
                "evidence_strength": "none"}
    d = item["data"]
    status = d.get("delivery_status") or ("delivered" if d.get("delivered") else "")
    zip_match = d.get("zip_match")
    signed = d.get("signature_on_file", False)
    strength = item["strength_label"]

    if status == "delivered" and signed and zip_match:
        base = {"score": -0.9, "reason": "delivered_signed_correct_address"}
    elif status == "delivered" and zip_match:
        base = {"score": -0.5, "reason": "delivered_correct_address_no_signature"}
    elif status == "delivered" and zip_match is False:
        base = {"score": 0.8, "reason": "delivered_wrong_address"}
    elif status == "in_transit":
        base = {"score": 0.3, "reason": "still_in_transit"}
    elif status in ("lost", "returned"):
        base = {"score": 0.8, "reason": f"carrier_status_{status}"}
    elif status == "delivered":
        base = {"score": -0.4, "reason": "delivered_address_unverified"}
    else:
        base = {"score": 0.0, "reason": "inconclusive"}

    # For quality categories delivery confirms receipt, not condition:
    if category.startswith("QD") and base["score"] < 0:
        base["score"] = max(base["score"], -0.5)
        base["reason"] += "_does_not_address_condition"
    # For partial-receipt disputes delivery confirms a package arrived,
    # not that all items were in it — the contents count is what's material:
    if category == "NR-02" and base["score"] < 0:
        base["score"] = max(base["score"] * 0.35, -0.3)
        base["reason"] += "_does_not_address_contents"
    # familiar address strengthens delivery for NR
    if (category.startswith("NR") and base["score"] < 0 and
            graph.get("address_familiarity_deliveries", 0) >= 3):
        base["score"] = min(base["score"] - 0.05, -0.05)
        base["reason"] += "_familiar_address"
    base["evidence_strength"] = strength
    return base


def score_product_condition(scored, graph, category, dispute):
    photos = scored.get("cardholder_photos")
    img = (photos or {}).get("data", {}).get("image_analysis") or {}
    if not img:
        stmt = _ev(scored, "cardholder_statement", "packaging_photos")
        if category.startswith("QD") and stmt is None:
            return {"score": 0.0, "reason": "no_image_evidence",
                    "evidence_strength": "none"}
        if stmt is not None:
            return {"score": 0.25, "reason": "cardholder_statement_only",
                    "evidence_strength": stmt["strength_label"]}
        return {"score": 0.0, "reason": "no_condition_evidence",
                "evidence_strength": "none"}
    if img.get("product_match") is False:
        if category == "QD-05":
            return {"score": 0.7, "reason": "image_confirms_wrong_item",
                    "evidence_strength": photos["strength_label"],
                    "detail": "Photo shows a different product than the listing "
                              "— consistent with a wrong-item claim"}
        return {"score": -0.5, "reason": "image_product_mismatch",
                "evidence_strength": "weak",
                "detail": "Uploaded photo does not match the disputed product"}
    if category == "QD-05" and img.get("product_match") is None:
        return {"score": 0.0, "reason": "product_match_inconclusive",
                "evidence_strength": "weak",
                "detail": "Photo similarity is borderline — cannot confirm or "
                          "refute which product was received"}
    damage = img.get("damage_assessment") or {}
    if damage.get("has_damage"):
        severity = damage.get("severity_score", 0.5)
        # Minor damage against a passing pre-shipment inspection is genuinely
        # contested: cosmetic damage can equally arise after delivery, so the
        # merchant's QC record is not rebutted by it.  Cap the contribution so
        # the case lands in the escalation band rather than auto-resolving.
        qc = _ev(scored, "qc_records", "pre_shipment_inspection",
                 "merchant_inspection_records")
        if (damage.get("severity_label") == "minor" and qc is not None
                and str((qc["data"] or {}).get("pre_shipment_inspection",
                                               "")).lower() == "pass"):
            return {"score": 0.15,
                    "reason": "minor_damage_contested_by_pre_shipment_qc",
                    "evidence_strength": photos["strength_label"],
                    "detail": "Only minor damage is visible and the merchant "
                              "holds a passing pre-shipment inspection — the "
                              "condition on arrival cannot be settled from "
                              "this evidence alone"}
        score = min(0.3 + severity * 0.65, 0.95)
        extra = graph.get("same_product_damage_reports", 0)
        detail = damage.get("damage_description", "")
        if extra >= 2:
            score = min(score + 0.05, 0.98)
            detail += f" | graph: {extra} other card members reported damage on the same product"
        return {"score": round(score, 2),
                "reason": f"damage_verified_{damage.get('severity_label', 'moderate')}",
                "evidence_strength": photos["strength_label"],
                "detail": detail}
    if category in ("QD-01", "QD-02", "QD-06"):
        return {"score": -0.3, "reason": "no_damage_visible",
                "evidence_strength": photos["strength_label"]}
    return {"score": 0.0, "reason": "no_damage_claimed_or_material",
            "evidence_strength": photos["strength_label"]}


def _amount_subchecks(scored, category, charged_amount):
    """Category-specific amount/log checks that don't need related txns."""
    auth = _ev(scored, "authorization_log")
    if auth and category in ("BA-02", "BA-06"):
        a = auth["data"]
        if a.get("authorized_amount") is not None and charged_amount is not None:
            if abs(a["authorized_amount"] - charged_amount) > 0.01:
                return {"score": 0.8, "reason": "charge_exceeds_authorization",
                        "evidence_strength": auth["strength_label"],
                        "detail": f"authorized {a['authorized_amount']}, "
                                  f"charged {charged_amount}"}
            return {"score": -0.7, "reason": "charge_matches_authorization",
                    "evidence_strength": auth["strength_label"]}
    atm = _ev(scored, "atm_terminal_logs")
    if atm and category == "SP-08":
        a = atm["data"]
        if a.get("dispensed_amount") is not None and charged_amount is not None:
            if a["dispensed_amount"] < charged_amount:
                return {"score": 0.85, "reason": "atm_short_dispense",
                        "evidence_strength": atm["strength_label"],
                        "detail": f"debited {charged_amount}, "
                                  f"dispensed {a['dispensed_amount']}"}
            return {"score": -0.8, "reason": "atm_full_dispense_logged",
                    "evidence_strength": atm["strength_label"]}
    inst = _ev(scored, "installment_agreement")
    if inst and category == "BA-07":
        a = inst["data"]
        if a.get("agreed_emi") is not None and a.get("charged_emi") is not None:
            if abs(a["agreed_emi"] - a["charged_emi"]) > 0.01:
                return {"score": 0.75, "reason": "installment_terms_mismatch",
                        "evidence_strength": inst["strength_label"],
                        "detail": f"agreed EMI {a['agreed_emi']}, "
                                  f"charged {a['charged_emi']}"}
            return {"score": -0.6, "reason": "installment_terms_match",
                    "evidence_strength": inst["strength_label"]}
    gw = _ev(scored, "payment_gateway_logs")
    if gw and category == "BA-05":
        a = gw["data"]
        if a.get("posting_error") is True or (a.get("expected") == "credit"
                                              and a.get("posted") == "charge"):
            return {"score": 0.8, "reason": "gateway_posting_error",
                    "evidence_strength": gw["strength_label"]}
        if a.get("posting_error") is False:
            return {"score": -0.6, "reason": "gateway_posting_correct",
                    "evidence_strength": gw["strength_label"]}
    fulfil = _ev(scored, "merchant_fulfillment_status")
    if fulfil and category == "NR-02":
        a = fulfil["data"]
        io, idl = a.get("items_ordered"), a.get("items_delivered")
        if io is not None and idl is not None:
            if idl < io:
                return {"score": 0.7, "reason": "partial_fulfillment_confirmed",
                        "evidence_strength": fulfil["strength_label"],
                        "detail": f"{idl}/{io} items delivered per merchant records"}
            return {"score": -0.6, "reason": "full_fulfillment_confirmed",
                    "evidence_strength": fulfil["strength_label"]}
    return None


def score_transaction_pattern(scored, graph, category, dispute):
    sub = _amount_subchecks(scored, category, dispute.get("amount"))
    item = _ev(scored, "all_transactions_same_merchant_7d", "related_transactions")
    if item is None:
        return sub or {"score": 0.0, "reason": "no_related_txns",
                       "evidence_strength": "none"}
    d = item["data"]
    disputed = d.get("disputed_transaction") or {}
    related = d.get("transactions", [])
    same_amount = [t for t in related
                   if t["amount"] == disputed.get("amount")
                   and t["id"] != disputed.get("id")]
    if same_amount and disputed.get("timestamp"):
        d_time = datetime.fromisoformat(disputed["timestamp"])
        gaps = [abs((d_time - datetime.fromisoformat(t["timestamp"])).total_seconds())
                for t in same_amount]
        min_gap = min(gaps)
        if min_gap < 300:
            return {"score": 0.9, "reason": "duplicate_within_5_min",
                    "evidence_strength": item["strength_label"],
                    "detail": f"matching charge {min_gap:.0f}s apart"}
        if min_gap < 86400:
            return {"score": 0.5, "reason": "similar_charge_within_24h",
                    "evidence_strength": item["strength_label"],
                    "detail": f"matching charge {min_gap/3600:.1f}h apart"}
        return {"score": 0.15, "reason": "similar_charge_same_week",
                "evidence_strength": item["strength_label"]}
    if category == "BA-01":
        return {"score": -0.7, "reason": "no_duplicate_pattern",
                "evidence_strength": item["strength_label"]}
    if sub:
        return sub
    return {"score": 0.0, "reason": "no_pattern_signal", "evidence_strength":
            item["strength_label"]}


MERCHANT_DOC_TYPES = [
    "authorization_log", "emv_chip_data", "pos_signed_receipt", "pos_terminal_logs",
    "receipt_data", "invoice_per_charge", "payment_gateway_logs", "qc_records",
    "pre_shipment_inspection", "merchant_inspection_records", "packaging_standards",
    "merchant_fulfillment_status", "rental_agreement", "damage_acknowledgement",
    "hotel_folio", "booking_confirmation", "airline_ticket_records",
    "installment_agreement", "dcc_consent_record", "currency_conversion_record",
    "brand_authentication", "atm_terminal_logs", "warranty_records",
    "product_specs", "no_show_policy", "promotional_terms", "insurance_claim_record",
    "other_payment_proof", "subscription_history",
]
CARDHOLDER_DOC_TYPES = [
    "cardholder_photos", "packaging_photos", "cardholder_statement",
    "cardholder_screenshot", "return_shipping_proof", "order_confirmation_email",
    "other_payment_proof", "brand_authentication",
]


def _doc_side_score(scored, types, burden_on_this_side: bool):
    present = [(t, scored[t]) for t in types
               if t in scored and scored[t]["strength_label"] != "none"]
    if not present:
        return None, []
    avg = sum(s["final_strength"] for _, s in present) / len(present)
    return avg, [t for t, _ in present]


def score_merchant_documentation(scored, graph, category, dispute):
    avg, types = _doc_side_score(scored, MERCHANT_DOC_TYPES, True)
    burden_merchant = _burden(category)["bearer"] == "merchant"
    if avg is None:
        if burden_merchant:
            return {"score": 0.6, "reason": "merchant_docs_absent_burden_unmet",
                    "evidence_strength": "none"}
        return {"score": 0.2, "reason": "merchant_docs_absent",
                "evidence_strength": "none"}
    score = -min(avg, 0.95)          # strong merchant docs favour merchant
    if not burden_merchant:
        score *= 0.7
    return {"score": round(score, 2), "reason": "merchant_docs_present",
            "evidence_strength": "strong" if avg >= 0.8 else
            "moderate" if avg >= 0.5 else "weak",
            "detail": f"{len(types)} merchant document types, avg strength {avg:.2f}"}


def score_cardholder_documentation(scored, graph, category, dispute):
    avg, types = _doc_side_score(scored, CARDHOLDER_DOC_TYPES, False)
    if avg is None:
        burden_ch = _burden(category)["bearer"] == "cardholder"
        if burden_ch:
            return {"score": -0.4, "reason": "cardholder_docs_absent_burden_unmet",
                    "evidence_strength": "none"}
        return {"score": 0.0, "reason": "cardholder_docs_absent",
                "evidence_strength": "none"}
    return {"score": round(min(avg, 0.95), 2), "reason": "cardholder_docs_present",
            "evidence_strength": "strong" if avg >= 0.8 else
            "moderate" if avg >= 0.5 else "weak",
            "detail": f"{len(types)} cardholder document types, avg strength {avg:.2f}"}


def score_communication_records(scored, graph, category, dispute):
    cancel = _ev(scored, "cancellation_records", "cancellation_confirmation")
    if cancel:
        d = cancel["data"]
        if d.get("cancelled_before_charge") or d.get("confirmation_number"):
            return {"score": 0.85, "reason": "cancellation_confirmed_before_charge",
                    "evidence_strength": cancel["strength_label"],
                    "detail": d.get("confirmation_number", "")}
        if d.get("cancelled_before_charge") is False:
            return {"score": -0.6, "reason": "cancellation_after_charge",
                    "evidence_strength": cancel["strength_label"]}
    promise = _ev(scored, "refund_promise_email")
    if promise:
        return {"score": 0.7, "reason": "merchant_promised_refund_in_writing",
                "evidence_strength": promise["strength_label"]}
    thread = _ev(scored, "communication_thread", "delay_notification",
                 "travel_disruption_record")
    if thread:
        d = thread["data"]
        direction = d.get("supports", "")
        if direction == "cardholder":
            return {"score": 0.45, "reason": "communications_support_cardholder",
                    "evidence_strength": thread["strength_label"]}
        if direction == "merchant":
            return {"score": -0.45, "reason": "communications_support_merchant",
                    "evidence_strength": thread["strength_label"]}
        return {"score": 0.0, "reason": "communications_neutral",
                "evidence_strength": thread["strength_label"]}
    return {"score": 0.0, "reason": "no_communication_records",
            "evidence_strength": "none"}


def score_historical_pattern(scored, graph, category, dispute):
    """Symmetric & capped: breaks near-ties, never decides a case (weight <=0.15
    in every profile; magnitudes here stay small)."""
    score, notes = 0.0, []
    loss_rate = graph.get("merchant_loss_rate", 0.0)
    dispute_rate = graph.get("merchant_dispute_rate", 0.0)
    if graph.get("merchant_dispute_ct", 0) >= 5:
        if loss_rate >= 0.7:
            score += 0.5; notes.append(f"merchant loses {loss_rate:.0%} of disputes")
        elif loss_rate <= 0.2 and dispute_rate < 0.01:
            score -= 0.3; notes.append("merchant rarely disputed and rarely loses")
    if dispute_rate >= 0.05:
        score += 0.3; notes.append(f"elevated merchant dispute rate {dispute_rate:.1%}")
    prior = graph.get("prior_disputes", [])
    resolved = [p for p in prior if p.get("outcome")]
    if len(resolved) >= 3:
        ch_losses = sum(1 for p in resolved if p["outcome"] == "favor_merchant")
        if ch_losses / len(resolved) >= 0.6:
            score -= 0.4; notes.append("filer has lost most prior disputes")
        elif ch_losses == 0:
            score += 0.15; notes.append("filer's prior disputes were upheld")
    score = max(-0.6, min(0.6, score))
    return {"score": round(score, 2),
            "reason": "; ".join(notes) if notes else "no_material_history",
            "evidence_strength": "moderate" if notes else "none"}


def score_policy_compliance(scored, graph, category, dispute):
    pol = _ev(scored, "merchant_return_policy", "merchant_terms_of_service",
              "no_show_policy", "promotional_terms", "dcc_consent_record")
    if pol is None:
        return {"score": 0.0, "reason": "no_policy_on_file", "evidence_strength": "none"}
    d = pol["data"]
    window = d.get("return_window_days")
    days = dispute.get("days_since_purchase")
    if window is not None and days is not None:
        if days <= window:
            return {"score": 0.7, "reason": "within_merchant_policy_window",
                    "evidence_strength": pol["strength_label"],
                    "detail": f"day {days:.0f} of a {window}-day policy"}
        return {"score": -0.5, "reason": "outside_merchant_policy_window",
                "evidence_strength": pol["strength_label"],
                "detail": f"day {days:.0f}, policy window {window} days"}
    if d.get("disclosed") is False:
        return {"score": 0.6, "reason": "policy_terms_not_disclosed",
                "evidence_strength": pol["strength_label"]}
    if d.get("disclosed") is True:
        return {"score": -0.4, "reason": "policy_terms_disclosed",
                "evidence_strength": pol["strength_label"]}
    return {"score": 0.0, "reason": "policy_neutral",
            "evidence_strength": pol["strength_label"]}


def score_digital_access_logs(scored, graph, category, dispute):
    logs = _ev(scored, "digital_access_logs", "download_delivery_logs",
               "account_provisioning_records", "login_ip_device_data")
    if logs is None:
        if category in ("NR-04",):
            return {"score": 0.7, "reason": "no_access_logs_burden_unmet",
                    "evidence_strength": "none"}
        return {"score": 0.0, "reason": "digital_logs_not_material",
                "evidence_strength": "none"}
    d = logs["data"]
    if d.get("accessed") or d.get("downloaded") or d.get("provisioned"):
        return {"score": -0.85, "reason": "access_logs_show_usage",
                "evidence_strength": logs["strength_label"],
                "detail": d.get("detail", "delivery/usage recorded in platform logs")}
    return {"score": 0.7, "reason": "logs_show_no_access_or_delivery",
            "evidence_strength": logs["strength_label"]}


def score_image_visual_analysis(scored, graph, category, dispute):
    photos = scored.get("cardholder_photos")
    img = (photos or {}).get("data", {}).get("image_analysis") or {}
    if not img:
        return {"score": 0.0, "reason": "no_image_evidence", "evidence_strength": "none"}
    stage_a = img.get("stage_a_product_verification", {})
    if img.get("product_match") is False:
        return {"score": -0.6, "reason": "image_product_mismatch",
                "evidence_strength": "weak",
                "detail": f"combined similarity {stage_a.get('combined_score')} "
                          f"< {stage_a.get('threshold')}"}
    damage = img.get("damage_assessment") or {}
    if damage.get("has_damage"):
        sev = damage.get("severity_score", 0.5)
        return {"score": round(0.35 + 0.6 * sev, 2),
                "reason": f"visual_damage_{damage.get('severity_label')}",
                "evidence_strength": photos["strength_label"],
                "detail": damage.get("damage_description", "")}
    if category.startswith("QD"):
        return {"score": -0.35, "reason": "image_verified_no_damage",
                "evidence_strength": photos["strength_label"]}
    return {"score": 0.1, "reason": "image_verified_product",
            "evidence_strength": photos["strength_label"]}


DIMENSION_SCORERS = {
    "delivery_proof": score_delivery_proof,
    "product_condition": score_product_condition,
    "transaction_pattern": score_transaction_pattern,
    "merchant_documentation": score_merchant_documentation,
    "cardholder_documentation": score_cardholder_documentation,
    "communication_records": score_communication_records,
    "historical_pattern": score_historical_pattern,
    "policy_compliance": score_policy_compliance,
    "digital_access_logs": score_digital_access_logs,
    "image_visual_analysis": score_image_visual_analysis,
}


@lru_cache(maxsize=1)
def _burden_cfg() -> dict:
    with open(CONFIG_DIR / "burden_of_proof.yaml") as f:
        return yaml.safe_load(f)


def _burden(category: str) -> dict:
    cfg = _burden_cfg()
    return cfg["categories"].get(category, cfg["default"])


# --------------------------------------------------------- conflict detection
CONFLICT_PAIRS = [
    ({"NR-01"}, {"QD-01", "QD-02", "QD-03", "QD-04", "QD-05", "QD-06"},
     "claims item never arrived AND describes the received item's condition"),
    ({"NR-01"}, {"CR-01"}, "claims non-receipt AND claims a return was shipped back"),
    ({"NR-01"}, {"NR-05"}, "claims never received AND claims late delivery"),
    ({"CR-06"}, {"QD-01"}, "claims refusal at delivery AND damage after opening"),
]


def detect_conflicts(codes: list[str]) -> list[dict]:
    s, out = set(codes), []
    for a, b, msg in CONFLICT_PAIRS:
        if s & a and s & b:
            out.append({"codes": sorted((s & a) | (s & b)), "conflict": msg})
    return out


# --------------------------------------------------------------- decision core
def make_decision(scored_evidence: dict, category: str, graph_context: dict,
                  dispute: dict) -> dict:
    profile_name, weights = weights_for(category)
    graph = _blind(dict(graph_context))
    graph.update({k: graph_context.get(k) for k in (
        "merchant_dispute_rate", "merchant_loss_rate", "merchant_dispute_ct",
        "address_familiarity_deliveries", "same_product_damage_reports",
        "prior_disputes", "prior_same_macro_category")})
    scored = scored_evidence["scored"]

    factors, weighted_sum = {}, 0.0
    for dimension, weight in weights.items():
        result = DIMENSION_SCORERS[dimension](scored, graph, category, dispute)
        factors[dimension] = {
            "direction_score": round(result["score"], 3),
            "evidence_strength": result.get("evidence_strength", "moderate"),
            "weight": weight,
            "weighted": round(result["score"] * weight, 4),
            "reason": result["reason"],
            "detail": result.get("detail", ""),
        }
        weighted_sum += result["score"] * weight

    return {
        "final_score": round(weighted_sum, 3),
        "factor_breakdown": factors,
        "category": category,
        "weight_profile": profile_name,
        "burden_of_proof": {**_burden(category), "category": category},
        "fairness": {
            "demographic_blindness": sorted(BLINDED_FIELDS),
            "merchant_history_weight": weights.get("historical_pattern", 0.0),
            "note": "Identity attributes are stripped before scoring; merchant "
                    "history is symmetric, capped, and breaks near-ties only.",
        },
    }


def run(ctx) -> dict:
    cls = ctx.stages["classification"]
    scored = ctx.stages["evidence_scoring"]
    graph = ctx.stages["graph_context"]

    primary_code = cls.get("primary_code") or "AR-01"
    primary = make_decision(scored, primary_code, graph, ctx.dispute)

    active_codes = [c["code"] for c in cls.get("categories", [])
                    if c.get("code")] or [primary_code]
    conflicts = detect_conflicts(active_codes)

    sub_decisions = []
    for code in active_codes:
        if code != primary_code:
            sub = make_decision(scored, code, graph, ctx.dispute)
            sub_decisions.append(sub)

    if sub_decisions:
        parts = [primary["final_score"]] + [s["final_score"] for s in sub_decisions]
        confs = [cls["confidence"]] + [
            c["confidence"] for c in cls.get("categories", [])[1:len(parts)]]
        total_w = sum(confs[:len(parts)]) or 1.0
        composite = sum(p * w for p, w in zip(parts, confs)) / total_w
    else:
        composite = primary["final_score"]

    # ---- conclusive-evidence rule (config: conclusive_floors) -------------
    th = _thresholds()
    floors = th.get("conclusive_floors", {}) or {}
    delivery_cats = set(th.get("conclusive_delivery_categories", []))
    conclusive = []
    for fname, f in primary["factor_breakdown"].items():
        reason = f.get("reason")
        if reason not in floors:
            continue
        if reason == "delivered_signed_correct_address" and \
                primary_code not in delivery_cats:
            continue
        conclusive.append({"factor": fname, "reason": reason,
                           "floor": floors[reason]})
    if conclusive and not conflicts:
        pos = [c["floor"] for c in conclusive if c["floor"] > 0]
        neg = [c["floor"] for c in conclusive if c["floor"] < 0]
        if pos and not neg:
            composite = max(composite, max(pos))
        elif neg and not pos:
            composite = min(composite, min(neg))
        # conclusive facts in BOTH directions -> no floor; analysts decide

    return {
        **primary,
        "composite_score": round(composite, 3),
        "conclusive_evidence": conclusive,
        "multi_category": len(sub_decisions) > 0,
        "sub_decisions": sub_decisions,
        "conflicts": conflicts,
        "conflict_hold": bool(conflicts),
    }
