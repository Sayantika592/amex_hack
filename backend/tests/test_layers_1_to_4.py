"""Layers 1-4: classification, evidence mapping, scoring."""
from backend.models.classification.factory import get_classifier
from backend.pipeline.layer2_evidence_mapping import get_evidence_requirements
from backend.pipeline.layer4_scoring import score_evidence
from backend.taxonomy import techdoc


def _labels():
    return list(techdoc.CODE_TO_LABEL.values())


def _label_to_code(label):
    return techdoc.LABEL_TO_CODE.get(label)


def test_classifier_rahul_text_is_qd01():
    clf = get_classifier()
    res = clf.classify(
        "Laptop screen was cracked when I opened the box. It looks like it "
        "was damaged during shipping.", _labels(), _label_to_code)
    assert res.primary_code == "QD-01"
    assert res.confidence >= 0.65
    assert res.status == "auto_classified"


def test_classifier_duplicate_charge():
    clf = get_classifier()
    res = clf.classify(
        "I was charged twice for the same order — two identical charges "
        "minutes apart.", _labels(), _label_to_code)
    assert res.primary_code == "BA-01"


def test_classifier_vague_text_flags_low_confidence():
    clf = get_classifier()
    res = clf.classify("something is wrong with my bill",
                       _labels(), _label_to_code)
    assert res.status in ("unclassified", "needs_review")
    assert (res.confidence or 0) < 0.65


def test_classifier_override_of_wrong_dropdown():
    """User picks 'not received' but describes damage -> classifier corrects."""
    clf = get_classifier()
    res = clf.classify(
        "The item arrived broken, the screen is cracked and unusable.",
        _labels(), _label_to_code, user_code="NR-01")
    assert res.primary_code == "QD-01"
    assert getattr(res, "override", False) or res.primary_code != "NR-01"


def test_evidence_mapping_is_network_specific():
    amex = get_evidence_requirements("NR-01", "amex")
    visa = get_evidence_requirements("NR-01", "visa")
    assert "shipping_tracking" in amex["required_evidence"]
    assert amex["required_evidence"] != visa["required_evidence"]
    assert amex["network"] == "amex"


def test_evidence_mapping_unclassified_uses_generic_path():
    from backend.pipeline import layer2_evidence_mapping as l2
    from backend.pipeline.context import PipelineContext
    ctx = PipelineContext(dispute={"network": "amex"})
    ctx.stages["classification"] = {"status": "unclassified", "primary_code": None,
                                    "categories": []}
    out = l2.run(ctx)
    assert out["union_required"], "generic path must still request evidence"
    assert "generic" in out["primary"]["source"]


def test_scoring_strong_vs_weak():
    bundle = {"collected": {
        "shipping_tracking": {"delivery_status": "delivered", "zip_match": True,
                              "signature_on_file": True, "dated": True},
        "cardholder_screenshot": {"dated": False},
    }}
    scored = score_evidence(bundle)["scored"]
    strong = scored["shipping_tracking"]["final_strength"]
    weak = scored["cardholder_screenshot"]["final_strength"]
    assert strong >= 0.8
    assert weak < 0.5
    assert scored["shipping_tracking"]["strength_label"] == "strong"


def test_scoring_zip_mismatch_penalised():
    ok = score_evidence({"collected": {"shipping_tracking": {
        "delivery_status": "delivered", "zip_match": True}}})["scored"]
    bad = score_evidence({"collected": {"shipping_tracking": {
        "delivery_status": "delivered", "zip_match": False}}})["scored"]
    assert bad["shipping_tracking"]["final_strength"] < \
        ok["shipping_tracking"]["final_strength"]


def test_scoring_missing_evidence_is_none():
    scored = score_evidence({"collected": {
        "delivery_confirmation": {"status": "not_available"}}})["scored"]
    assert scored["delivery_confirmation"]["strength_label"] == "none"
    assert scored["delivery_confirmation"]["final_strength"] == 0.0
