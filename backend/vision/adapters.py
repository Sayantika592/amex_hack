"""Image damage-detection pipeline (TDD §13) with the AI_MODE switch.

Stage A — Product verification:  does the uploaded photo show the product
           from the transaction?  REAL mode: OpenAI CLIP ViT-L/14, dual check
           (image-image 60% + image-text 40%), threshold 0.70.
Stage B — Damage assessment:      REAL mode: Salesforce BLIP-2 (OPT-2.7B)
           visual question answering (damaged? / describe / severity /
           consistency), strength 0.65 into evidence scoring.

DEMO mode (DeterministicVision): synthetic photos carry an *observable content
descriptor* — what a vision model would see in the pixels (visible damage,
severity, whether it matches the listing), generated with realistic noise
relative to ground truth.  The deterministic adapter analyzes that descriptor
and emits the exact same output schema.  It never reads ground_truth.csv and
never claims CLIP/BLIP-2 ran: mode="demo" flows through to the UI.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache

from backend.config import settings
from backend.vision import pixels

CLIP_CHECKPOINT = "openai/clip-vit-large-patch14"
BLIP2_CHECKPOINT = "Salesforce/blip2-opt-2.7b"
# VRAM needed (fp16) for the damage-assessment model, GB
VQA_VRAM_GB = {"Salesforce/blip2-opt-2.7b": 8.0,
               "Salesforce/blip2-flan-t5-xl": 9.0,
               "Salesforce/blip-vqa-base": 1.5,
               "Salesforce/blip-vqa-capfilt-large": 2.5}


def available_vram_gb() -> float | None:
    """Total VRAM on the default CUDA device, or None if there is no GPU."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        return torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    except Exception:
        return None
MATCH_THRESHOLD = 0.70


class VisionBase:
    name = "base"
    mode = "demo"

    def verify_product(self, photo: dict, listing: dict) -> dict:
        raise NotImplementedError

    def assess_damage(self, photo: dict, product_type: str) -> dict:
        raise NotImplementedError

    def analyze(self, photo: dict, listing: dict, product_type: str) -> dict:
        stage_a = self.verify_product(photo, listing)
        result = {"stage_a_product_verification": stage_a,
                  "product_match": stage_a["product_match"],
                  "model": self.name, "mode": self.mode}
        if stage_a["product_match"]:
            result["stage_b_damage_assessment"] = self.assess_damage(photo, product_type)
            result["damage_assessment"] = result["stage_b_damage_assessment"]
        else:
            result["stage_b_damage_assessment"] = {
                "skipped": True,
                "reason": "Stage A flagged possible product mismatch; damage "
                          "assessment only runs on verified product images."}
            result["damage_assessment"] = {}
        return result


class CLIPBLIP2Vision(VisionBase):
    """REAL mode — requires torch + transformers + model weights."""
    name = f"CLIP {CLIP_CHECKPOINT} + BLIP-2 {BLIP2_CHECKPOINT}"
    mode = "real"

    def __init__(self, vqa_checkpoint: str | None = None):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        self.vqa_checkpoint = vqa_checkpoint or settings.vision_vqa_model
        self.clip = CLIPModel.from_pretrained(CLIP_CHECKPOINT)
        self.clip_proc = CLIPProcessor.from_pretrained(CLIP_CHECKPOINT)

        cuda = torch.cuda.is_available()
        dtype = torch.float16 if cuda else torch.float32
        need = VQA_VRAM_GB.get(self.vqa_checkpoint, 8.0)
        have = available_vram_gb()
        if have is not None and have < need:
            raise RuntimeError(
                f"{self.vqa_checkpoint} needs about {need:.0f} GB of VRAM but "
                f"this GPU has {have:.1f} GB. Set "
                f"VISION_VQA_MODEL=Salesforce/blip-vqa-base (~1.5 GB) to run "
                f"damage assessment for real on this card.")

        if "blip2" in self.vqa_checkpoint:
            from transformers import (Blip2ForConditionalGeneration,
                                      Blip2Processor)
            self.blip_proc = Blip2Processor.from_pretrained(self.vqa_checkpoint)
            self.blip = Blip2ForConditionalGeneration.from_pretrained(
                self.vqa_checkpoint, torch_dtype=dtype)
        else:                       # BLIP-1 visual question answering
            from transformers import BlipForQuestionAnswering, BlipProcessor
            self.blip_proc = BlipProcessor.from_pretrained(self.vqa_checkpoint)
            self.blip = BlipForQuestionAnswering.from_pretrained(
                self.vqa_checkpoint, torch_dtype=dtype)
        if cuda:
            self.clip = self.clip.to("cuda")
            self.blip = self.blip.to("cuda")
        self.name = f"CLIP {CLIP_CHECKPOINT} + VQA {self.vqa_checkpoint}"

    def _open(self, ref: str):
        from PIL import Image
        return Image.open(ref).convert("RGB")

    def verify_product(self, photo, listing):
        torch = self.torch
        up = self._open(photo["image_ref"])
        li = self._open(listing["image_ref"])
        inputs = self.clip_proc(images=[up, li], return_tensors="pt")
        with torch.no_grad():
            feats = self.clip.get_image_features(**inputs)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            img_sim = float(feats[0] @ feats[1])
        ti = self.clip_proc(text=[listing.get("description", "")], images=[up],
                            return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            out = self.clip(**ti)
            txt_sim = float(out.logits_per_image[0][0]) / 100.0
        combined = 0.6 * img_sim + 0.4 * txt_sim
        return {"product_match": combined >= MATCH_THRESHOLD,
                "image_similarity": round(img_sim, 3),
                "text_similarity": round(txt_sim, 3),
                "combined_score": round(combined, 3),
                "threshold": MATCH_THRESHOLD}

    def _ask(self, image, question: str) -> str:
        torch = self.torch
        dtype = self.blip.dtype
        inputs = self.blip_proc(images=image, text=question, return_tensors="pt"
                                ).to(self.blip.device, dtype)
        with torch.no_grad():
            out = self.blip.generate(**inputs, max_new_tokens=40)
        return self.blip_proc.decode(out[0], skip_special_tokens=True)

    def assess_damage(self, photo, product_type):
        img = self._open(photo["image_ref"])
        a1 = self._ask(img, "Is this item damaged or broken? Answer yes or no.")
        result = {"has_damage": "yes" in a1.lower()}
        if result["has_damage"]:
            result["damage_description"] = self._ask(
                img, "Describe the damage visible in this image. Be specific.")
            sev = self._ask(img, "Rate the severity of damage: minor, moderate, "
                                 "or severe. Answer with one word.").strip().lower()
            smap = {"minor": 0.3, "moderate": 0.6, "severe": 0.9}
            result["severity_label"] = sev if sev in smap else "moderate"
            result["severity_score"] = smap.get(sev, 0.5)
        else:
            result["damage_description"] = "No visible damage"
            result["severity_label"] = "none"
            result["severity_score"] = 0.0
        result["consistency_check"] = self._ask(
            img, f"Is this a {product_type}? Answer yes or no.")
        return result


class DeterministicVision(VisionBase):
    """DEMO mode — classical computer vision on the actual image files.

    When the evidence carries a readable image path (the synthetic dataset
    renders real JPEGs), Stage A compares the card member's photo against the
    merchant's listing image on colour distribution and coarse structure, and
    Stage B looks for fracture signatures the listing does not have.  That is
    real pixel analysis: no model weights, no network, and no reading of any
    label — see backend/vision/pixels.py.

    Only if no image file is available does it fall back to the photo's
    observable content descriptor (older datasets, hand-seeded cases).

    Either way it reports mode="demo" and its own name — it is not CLIP and
    never claims to be.
    """
    name = "PixelVision (classical CV — colour/structure match + fracture detection)"
    mode = "demo"

    @staticmethod
    def _jitter(key: str, lo: float, hi: float) -> float:
        h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        return lo + h * (hi - lo)

    @staticmethod
    def _refs(photo, listing):
        p = str(photo.get("image_ref") or "")
        l = str(listing.get("image_ref") or "")
        if not p or not l or p.startswith("img://") or l.startswith("img://"):
            return None, None
        return p, l

    def verify_product(self, photo, listing):
        p_ref, l_ref = self._refs(photo, listing)
        if p_ref:
            result = pixels.verify(p_ref, l_ref)
            if result is not None:
                result["analysis"] = "pixels"
                return result
        return self._verify_from_descriptor(photo, listing)

    def assess_damage(self, photo, product_type):
        p_ref = str(photo.get("image_ref") or "")
        l_ref = str(self._listing_ref or "")
        if p_ref and l_ref and not p_ref.startswith("img://"):
            result = pixels.damage(p_ref, l_ref)
            if result is not None:
                result["analysis"] = "pixels"
                result["product_type_checked"] = product_type
                return result
        return self._damage_from_descriptor(photo, product_type)

    # the listing ref is needed as the damage baseline; analyze() sets it
    _listing_ref = None

    def analyze(self, photo, listing, product_type):
        self._listing_ref = listing.get("image_ref")
        try:
            return super().analyze(photo, listing, product_type)
        finally:
            self._listing_ref = None

    # ---------------------------------------------------- descriptor fallback
    def _verify_from_descriptor(self, photo, listing):
        content = photo.get("content", {})
        ref = str(photo.get("image_ref", "")) + str(listing.get("image_ref", ""))
        shows = content.get("shows_product", True)
        if shows is None:
            img_sim = self._jitter("i" + ref, 0.60, 0.72)
            txt_sim = self._jitter("t" + ref, 0.55, 0.70)
            combined = 0.6 * img_sim + 0.4 * txt_sim
            return {"product_match": None,
                    "image_similarity": round(img_sim, 3),
                    "text_similarity": round(txt_sim, 3),
                    "combined_score": round(combined, 3),
                    "threshold": MATCH_THRESHOLD,
                    "analysis": "content_descriptor (no image file available)",
                    "note": "borderline similarity — match inconclusive"}
        if shows:
            img_sim = self._jitter("i" + ref, 0.74, 0.93)
            txt_sim = self._jitter("t" + ref, 0.62, 0.88)
        else:
            img_sim = self._jitter("i" + ref, 0.18, 0.52)
            txt_sim = self._jitter("t" + ref, 0.15, 0.55)
        combined = 0.6 * img_sim + 0.4 * txt_sim
        return {"product_match": combined >= MATCH_THRESHOLD,
                "image_similarity": round(img_sim, 3),
                "text_similarity": round(txt_sim, 3),
                "combined_score": round(combined, 3),
                "threshold": MATCH_THRESHOLD,
                "analysis": "content_descriptor (no image file available)"}

    def _damage_from_descriptor(self, photo, product_type):
        content = photo.get("content", {})
        has_damage = bool(content.get("visible_damage", False))
        if not has_damage:
            return {"has_damage": False, "damage_description": "No visible damage",
                    "severity_label": "none", "severity_score": 0.0,
                    "consistency_check": "yes",
                    "analysis": "content_descriptor (no image file available)"}
        sev = content.get("severity_label", "moderate")
        smap = {"minor": 0.3, "moderate": 0.6, "severe": 0.9}
        return {"has_damage": True,
                "damage_description": content.get(
                    "damage_description", f"visible damage to the {product_type}"),
                "severity_label": sev,
                "severity_score": smap.get(sev, 0.5),
                "consistency_check": "yes",
                "analysis": "content_descriptor (no image file available)"}


_vision_warning = None


@lru_cache(maxsize=1)
def get_vision() -> VisionBase:
    """AI_MODE switch for the image pipeline.

      AI_MODE=real -> CLIP ViT-L/14 + BLIP-2 (falls back loudly if the
                      weights or torch are unavailable)
      AI_MODE=demo -> PixelVision (classical CV on the real image files)
    """
    global _vision_warning
    if settings.ai_mode == "real":
        try:
            return CLIPBLIP2Vision()
        except Exception as exc:
            _vision_warning = (f"AI_MODE=real requested but CLIP/BLIP-2 could not "
                               f"be loaded ({exc}); running PixelVision in DEMO "
                               f"mode instead.")
            print(f"[vision] WARNING: {_vision_warning}")
    return DeterministicVision()


def vision_info() -> list[dict]:
    v = get_vision()
    real = v.mode == "real"
    return [
        {"component": "image_verification_clip",
         "requested_mode": settings.ai_mode,
         "model": CLIP_CHECKPOINT if real else v.name,
         "mode": v.mode, "fallback_warning": _vision_warning},
        {"component": "damage_assessment_blip2",
         "requested_mode": settings.ai_mode,
         "model": getattr(v, "vqa_checkpoint", BLIP2_CHECKPOINT) if real else v.name,
         "mode": v.mode, "fallback_warning": _vision_warning},
    ]
