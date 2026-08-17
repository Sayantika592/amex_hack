"""Layer 1 — dispute classification.

spaCy produces structured NLP features (preprocessing / sentences / entities /
normalization); BART-large-MNLI (or the deterministic fallback in DEMO mode)
performs zero-shot classification against the INTERNAL 36-type taxonomy —
never directly against raw network codes.  The model does UNDERSTANDING; the
rule engine (Layers 6-8) does DECISION.
"""
from backend.models.classification.factory import get_classifier
from backend.nlp.factory import get_nlp
from backend.taxonomy.registry import get_registry


def run(ctx) -> dict:
    reg = get_registry()
    nlp = get_nlp()
    features = nlp.process(ctx.dispute.get("description", ""))
    clf = get_classifier()
    result = clf.classify(features.clean_text, reg.labels(), reg.label_to_code,
                          user_code=ctx.dispute.get("user_selected_code"))
    out = result.as_dict()
    # Network mapping step: internal type -> network reason code(s)
    network = ctx.dispute["network"]
    code = out["primary_code"] or ctx.dispute.get("user_selected_code")
    out["network_mapping"] = {
        "internal_code": code,
        "network": network,
        "network_reason_codes": reg.network_codes_for(code, network) if code else [],
        "note": "Internal type and network reason code are separate concepts; "
                "mapping is many-to-many per the supplied Excel.",
    }
    out["nlp_features"] = features.as_dict()
    return out
