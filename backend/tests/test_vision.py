"""The vision pipeline runs on real pixels in DEMO mode.

These tests render images and assert the classical-CV analyzer measures them
correctly — no descriptor flags involved.
"""
import tempfile
from pathlib import Path

import pytest

from backend.vision import pixels
from backend.vision.adapters import DeterministicVision, get_vision
from data.images import distinct_category, render_listing, render_photo


@pytest.fixture(scope="module")
def rendered():
    root = Path(tempfile.mkdtemp(prefix="vision-test-"))
    listing = render_listing(root, "P-TEST", "electronics")
    return {
        "root": root,
        "listing": listing,
        "clean": render_photo(root, "T-clean", "P-TEST", "electronics"),
        "severe": render_photo(root, "T-severe", "P-TEST", "electronics",
                               damage="severe"),
        "moderate": render_photo(root, "T-mod", "P-TEST", "electronics",
                                 damage="moderate"),
        "wrong": render_photo(root, "T-wrong", "P-TEST", "electronics",
                              wrong_product_id="P-OTHER",
                              wrong_category=distinct_category("electronics", "x")),
        "blurry": render_photo(root, "T-blur", "P-TEST", "electronics",
                               unclear=True),
    }


def test_images_are_real_files(rendered):
    for key in ("listing", "clean", "severe", "wrong", "blurry"):
        p = Path(rendered[key])
        assert p.exists() and p.stat().st_size > 1000, key


def test_same_product_verifies(rendered):
    r = pixels.verify(rendered["clean"], rendered["listing"])
    assert r["product_match"] is True
    assert r["combined_score"] >= r["threshold"]


def test_different_product_does_not_verify(rendered):
    r = pixels.verify(rendered["wrong"], rendered["listing"])
    assert r["product_match"] is not True       # False or inconclusive, never True


def test_blurred_photo_is_inconclusive_not_guessed(rendered):
    r = pixels.verify(rendered["blurry"], rendered["listing"])
    assert r["product_match"] is None
    assert "note" in r


def test_clean_photo_shows_no_damage(rendered):
    d = pixels.damage(rendered["clean"], rendered["listing"])
    assert d["has_damage"] is False
    assert d["severity_score"] == 0.0


def test_damage_severity_scales_with_visible_fractures(rendered):
    mod = pixels.damage(rendered["moderate"], rendered["listing"])
    sev = pixels.damage(rendered["severe"], rendered["listing"])
    assert mod["has_damage"] and sev["has_damage"]
    assert sev["damage_metric"] > mod["damage_metric"]
    assert sev["severity_label"] == "severe"


def test_adapter_uses_pixels_when_images_exist(rendered):
    v = DeterministicVision()
    out = v.analyze({"image_ref": rendered["severe"]},
                    {"image_ref": rendered["listing"]}, "electronics")
    assert out["stage_a_product_verification"]["analysis"] == "pixels"
    assert out["damage_assessment"]["analysis"] == "pixels"
    assert out["mode"] == "demo"


def test_adapter_falls_back_when_no_image_file():
    """Older records with img:// placeholders still work, and say so."""
    v = DeterministicVision()
    out = v.analyze({"image_ref": "img://nope.jpg",
                     "content": {"shows_product": True, "visible_damage": True,
                                 "severity_label": "severe"}},
                    {"image_ref": "img://listing.jpg"}, "electronics")
    assert "content_descriptor" in out["stage_a_product_verification"]["analysis"]
    assert out["damage_assessment"]["has_damage"] is True


def test_stage_b_skipped_when_product_unverified(rendered):
    v = DeterministicVision()
    out = v.analyze({"image_ref": rendered["wrong"]},
                    {"image_ref": rendered["listing"]}, "electronics")
    assert out["stage_b_damage_assessment"].get("skipped") is True


def test_demo_mode_never_claims_to_be_clip():
    v = get_vision()
    assert v.mode == "demo"
    assert "CLIP" not in v.name and "BLIP" not in v.name
