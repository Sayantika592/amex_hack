#!/usr/bin/env python
"""Pre-download and verify the REAL-mode models.

Run this ONCE on a machine with internet (at home, before travelling).  It
downloads the weights into the local Hugging Face cache and then actually
loads and exercises each one, so you know they work before you are standing
in front of a jury.

    python scripts/fetch_models.py                 # all three
    python scripts/fetch_models.py --only bart clip
    python scripts/fetch_models.py --verify-only   # no download, just check
    python scripts/fetch_models.py --cache-dir ./model-cache

At the venue, with no internet:

    export HF_HUB_OFFLINE=1
    export AI_MODE=real
    uvicorn backend.api.app:app --port 8000

The cache lives in $HF_HOME (default ~/.cache/huggingface).  If you pass
--cache-dir, export HF_HOME to that same path on the demo machine.

Approximate download sizes: BART-large-MNLI ~1.6 GB, CLIP ViT-L/14 ~1.7 GB,
BLIP-2 OPT-2.7B ~15 GB (fp32 download; loaded in fp16).  BLIP-2 needs a GPU
to be usable at demo speed — on CPU-only machines, fetch bart+clip and leave
damage assessment in DEMO mode, which the UI will report honestly.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os as _os

VQA_MODEL = _os.environ.get("VISION_VQA_MODEL", "Salesforce/blip2-opt-2.7b")
_VQA_SIZES = {"Salesforce/blip2-opt-2.7b": ("~15 GB", "~8 GB VRAM"),
              "Salesforce/blip2-flan-t5-xl": ("~16 GB", "~9 GB VRAM"),
              "Salesforce/blip-vqa-base": ("~1.5 GB", "~1.5 GB VRAM"),
              "Salesforce/blip-vqa-capfilt-large": ("~2.5 GB", "~2.5 GB VRAM")}
_vqa_disk, _vqa_vram = _VQA_SIZES.get(VQA_MODEL, ("unknown", "unknown"))

MODELS = {
    "bart": ("facebook/bart-large-mnli", "~1.6 GB", "dispute classification (Layer 1)"),
    "clip": ("openai/clip-vit-large-patch14", "~1.7 GB", "image verification (Stage A)"),
    "blip2": (VQA_MODEL, _vqa_disk, f"damage assessment (Stage B), needs {_vqa_vram}"),
}


def _ok(msg):
    print(f"  \033[32mPASS\033[0m {msg}")


def _fail(msg):
    print(f"  \033[31mFAIL\033[0m {msg}")


def fetch_bart(verify_only: bool) -> bool:
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              pipeline)
    ckpt = MODELS["bart"][0]
    tok = AutoTokenizer.from_pretrained(ckpt, local_files_only=verify_only)
    mdl = AutoModelForSequenceClassification.from_pretrained(
        ckpt, local_files_only=verify_only)
    pipe = pipeline("zero-shot-classification", model=mdl, tokenizer=tok, device=-1)
    t0 = time.time()
    out = pipe("Laptop screen was cracked when I opened the box.",
               candidate_labels=["Goods damaged on arrival", "Goods not received",
                                 "Duplicate charge"],
               hypothesis_template="This dispute is about {}.")
    dt = time.time() - t0
    top = out["labels"][0]
    _ok(f"BART-large-MNLI loaded — top label '{top}' "
        f"({out['scores'][0]:.2f}) in {dt:.1f}s on CPU")
    return top == "Goods damaged on arrival"


def fetch_clip(verify_only: bool) -> bool:
    import torch
    from transformers import CLIPModel, CLIPProcessor
    ckpt = MODELS["clip"][0]
    model = CLIPModel.from_pretrained(ckpt, local_files_only=verify_only)
    proc = CLIPProcessor.from_pretrained(ckpt, local_files_only=verify_only)
    listing, photo = _demo_image_pair()
    if listing is None:
        _ok("CLIP loaded (no generated images found to score against)")
        return True
    from PIL import Image
    ims = [Image.open(photo).convert("RGB"), Image.open(listing).convert("RGB")]
    t0 = time.time()
    with torch.no_grad():
        f = model.get_image_features(**proc(images=ims, return_tensors="pt"))
        f = f / f.norm(dim=-1, keepdim=True)
        sim = float(f[0] @ f[1])
    _ok(f"CLIP ViT-L/14 loaded — Rahul photo vs listing similarity "
        f"{sim:.3f} in {time.time() - t0:.1f}s")
    return True


def fetch_blip2(verify_only: bool) -> bool:
    import torch
    ckpt = MODELS["blip2"][0]
    cuda = torch.cuda.is_available()
    if cuda:
        from backend.vision.adapters import VQA_VRAM_GB, available_vram_gb
        have, need = available_vram_gb(), VQA_VRAM_GB.get(ckpt, 8.0)
        print(f"  GPU: {torch.cuda.get_device_name(0)} — {have:.1f} GB VRAM, "
              f"{ckpt} needs about {need:.1f} GB")
        if have < need:
            _fail(f"{ckpt} will not fit on this GPU. Re-run with:\n"
                  f"         VISION_VQA_MODEL=Salesforce/blip-vqa-base "
                  f"python scripts/fetch_models.py --only blip2")
            return False
    if "blip2" in ckpt:
        from transformers import (Blip2ForConditionalGeneration as VQAModel,
                                  Blip2Processor as VQAProcessor)
    else:
        from transformers import (BlipForQuestionAnswering as VQAModel,
                                  BlipProcessor as VQAProcessor)
    proc = VQAProcessor.from_pretrained(ckpt, local_files_only=verify_only)
    model = VQAModel.from_pretrained(
        ckpt, torch_dtype=torch.float16 if cuda else torch.float32)
    if cuda:
        model = model.to("cuda")
    listing, photo = _demo_image_pair()
    if photo is None:
        _ok(f"{ckpt} loaded ({'GPU' if cuda else 'CPU'}) — no image to caption")
        return True
    from PIL import Image
    img = Image.open(photo).convert("RGB")
    t0 = time.time()
    inputs = proc(images=img, text="Is this item damaged or broken?",
                  return_tensors="pt")
    if cuda:
        inputs = inputs.to("cuda", torch.float16)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=20)
    answer = proc.decode(out[0], skip_special_tokens=True)
    _ok(f"{ckpt} loaded on {'GPU' if cuda else 'CPU'} — answered "
        f"'{answer.strip()[:60]}' in {time.time() - t0:.1f}s")
    if not cuda:
        print("       NOTE: CPU inference is far too slow for a live demo; "
              "keep AI_MODE=demo for Stage B unless a GPU is present.")
    return True


def _demo_image_pair():
    from backend.paths import GENERATED_DATA_DIR
    root = GENERATED_DATA_DIR / "images"
    listing = root / "listings" / "P-DEMO-LAPTOP.jpg"
    photo = root / "photos" / "D-DEMO-RAHUL.jpg"
    if listing.exists() and photo.exists():
        return listing, photo
    return None, None


FETCHERS = {"bart": fetch_bart, "clip": fetch_clip, "blip2": fetch_blip2}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=list(MODELS),
                    help="fetch a subset (default: all)")
    ap.add_argument("--verify-only", action="store_true",
                    help="do not download; check the local cache only")
    ap.add_argument("--cache-dir", help="set HF_HOME to this directory")
    ap.add_argument("--vqa-model", help="damage-assessment checkpoint "
                    "(default $VISION_VQA_MODEL, or Salesforce/blip2-opt-2.7b). "
                    "On a <8 GB GPU use Salesforce/blip-vqa-base")
    args = ap.parse_args()

    if args.cache_dir:
        os.environ["HF_HOME"] = str(Path(args.cache_dir).resolve())
        print(f"HF_HOME = {os.environ['HF_HOME']}")
    if args.vqa_model:
        os.environ["VISION_VQA_MODEL"] = args.vqa_model
        size = _VQA_SIZES.get(args.vqa_model, ("unknown", "unknown"))
        MODELS["blip2"] = (args.vqa_model, size[0],
                           f"damage assessment (Stage B), needs {size[1]}")
    if args.verify_only:
        os.environ["HF_HUB_OFFLINE"] = "1"

    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        print("torch / transformers are not installed. Run:\n"
              "    pip install -r backend/requirements-ml.txt", file=sys.stderr)
        return 2

    wanted = args.only or list(MODELS)
    results = {}
    for key in wanted:
        ckpt, size, role = MODELS[key]
        print(f"\n=== {key}: {ckpt} ({size}) — {role}")
        try:
            results[key] = bool(FETCHERS[key](args.verify_only))
        except Exception as exc:
            _fail(f"{ckpt}: {type(exc).__name__}: {exc}")
            results[key] = False

    print("\n---------------- summary ----------------")
    for key in wanted:
        state = "READY" if results.get(key) else "NOT AVAILABLE"
        print(f"  {key:6s} {MODELS[key][0]:36s} {state}")
    ready = [k for k in wanted if results.get(k)]
    if ready:
        print("\nAt the venue (no internet needed):")
        print("    export HF_HUB_OFFLINE=1")
        if args.cache_dir:
            print(f"    export HF_HOME={os.environ['HF_HOME']}")
        print("    export AI_MODE=real")
        if MODELS["blip2"][0] != "Salesforce/blip2-opt-2.7b":
            print(f"    export VISION_VQA_MODEL={MODELS['blip2'][0]}")
        print("    uvicorn backend.api.app:app --port 8000")
        print("Then open /models in the UI — every component that actually "
              "loaded reports REAL; anything that did not falls back and says "
              "DEMO. The badge never lies.")
    if len(ready) < len(wanted):
        print("\nMissing models simply run in DEMO mode; the system stays "
              "fully functional and labels itself honestly.")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
