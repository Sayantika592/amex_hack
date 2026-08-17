"""Layer 2 — Network-Specific Evidence Mapping Matrix.

Configuration, not code: config/evidence_matrix.yaml.  A Visa rule change is
a one-row config edit; the classifier and collectors are untouched.

Also performs the NETWORK MAPPING step of the architecture:
    internal type + network  ->  network reason code(s)
using the Excel-supplied mapping (many-to-many aware).
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from backend.paths import CONFIG_DIR
from backend.taxonomy.registry import get_registry


@lru_cache(maxsize=1)
def _matrix() -> dict:
    with open(CONFIG_DIR / "evidence_matrix.yaml") as f:
        return yaml.safe_load(f)["categories"]


def get_evidence_requirements(category_code: str, network: str) -> dict:
    """What evidence is needed for this category on this network?"""
    mapping = _matrix().get(category_code, {})
    required = list(mapping.get("required", {}).get(network, []))
    reg = get_registry()
    return {
        "category": category_code,
        "network": network,
        "network_reason_codes": reg.network_codes_for(category_code, network),
        "required_evidence": required,
        "optional_evidence": list(mapping.get("optional", [])),
        "cardholder_requested": list(mapping.get("cardholder_requested", [])),
        "merchant_requested": list(mapping.get("merchant_requested", [])),
        "source": "config/evidence_matrix.yaml",
    }


GENERIC_PATH = {
    "category": None,
    "required_evidence": ["receipt_data", "related_transactions",
                          "communication_thread"],
    "optional_evidence": ["merchant_terms_of_service"],
    "cardholder_requested": ["describe_dispute_in_detail"],
    "merchant_requested": ["transaction_documentation"],
    "source": "generic_path (unclassified dispute)",
}


def run(ctx) -> dict:
    """Pipeline entry: ctx.classification -> requirements (multi-category aware:
    each sub-category gets its own requirement set; union feeds the collector)."""
    network = ctx.dispute["network"]
    cls = ctx.stages["classification"]
    if cls["status"] == "unclassified":
        req = {**GENERIC_PATH, "network": network, "network_reason_codes": []}
        return {"primary": req, "sub_requirements": [], "union_required":
                list(req["required_evidence"]), "union_optional":
                list(req["optional_evidence"])}

    primary = get_evidence_requirements(cls["primary_code"], network)
    subs = []
    for cat in cls.get("categories", [])[1:]:
        if cat.get("code") and cat["code"] != cls["primary_code"]:
            subs.append(get_evidence_requirements(cat["code"], network))

    union_req, union_opt, seen = [], [], set()
    for r in [primary] + subs:
        for e in r["required_evidence"]:
            if e not in seen:
                union_req.append(e); seen.add(e)
        for e in r["optional_evidence"]:
            if e not in seen:
                union_opt.append(e); seen.add(e)
    return {"primary": primary, "sub_requirements": subs,
            "union_required": union_req, "union_optional": union_opt}
