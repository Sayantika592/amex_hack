#!/usr/bin/env python
"""Delete the downloaded model weights and free the disk space.

Use this after the demo. It removes the Hugging Face cache entries for the
checkpoints this project downloads — nothing else on your machine is touched.

    python scripts/clean_models.py                 # show what would be freed
    python scripts/clean_models.py --yes           # actually delete
    python scripts/clean_models.py --all --yes     # whole HF cache, not just ours
    python scripts/clean_models.py --images --yes  # also the generated images

Re-downloading later is one command: python scripts/fetch_models.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUR_REPOS = [
    "facebook/bart-large-mnli",
    "openai/clip-vit-large-patch14",
    "Salesforce/blip2-opt-2.7b",
    "Salesforce/blip2-flan-t5-xl",
    "Salesforce/blip-vqa-base",
    "Salesforce/blip-vqa-capfilt-large",
]


def hub_dir() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    home = os.environ.get("HF_HOME")
    if home:
        return Path(home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def gb(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MB"
    return f"{n / 1024:.0f} KB"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true",
                    help="actually delete (default is a dry run)")
    ap.add_argument("--all", action="store_true",
                    help="remove the entire Hugging Face hub cache, not just "
                         "this project's checkpoints")
    ap.add_argument("--images", action="store_true",
                    help="also delete the generated evidence images "
                         "(regenerate with: python -m data.generate)")
    args = ap.parse_args()

    cache = hub_dir()
    targets: list[tuple[str, Path, int]] = []

    if not cache.exists():
        print(f"No Hugging Face cache at {cache} — nothing to remove.")
    elif args.all:
        targets.append(("entire Hugging Face hub cache", cache, dir_size(cache)))
    else:
        for repo in OUR_REPOS:
            d = cache / ("models--" + repo.replace("/", "--"))
            if d.exists():
                targets.append((repo, d, dir_size(d)))

    if args.images:
        from backend.paths import GENERATED_DATA_DIR
        imgs = GENERATED_DATA_DIR / "images"
        if imgs.exists():
            targets.append(("generated evidence images", imgs, dir_size(imgs)))

    if not targets:
        print("Nothing to delete — no cached checkpoints found in "
              f"{cache}")
        return 0

    total = sum(t[2] for t in targets)
    print(f"Cache location: {cache}\n")
    for name, path, size in targets:
        print(f"  {gb(size):>10}  {name}")
        print(f"              {path}")
    print(f"\n  {gb(total):>10}  TOTAL")

    if not args.yes:
        print("\nDry run — nothing deleted. Re-run with --yes to remove.")
        return 0

    freed = 0
    for name, path, size in targets:
        try:
            shutil.rmtree(path)
            freed += size
            print(f"removed {name}")
        except OSError as exc:
            print(f"could not remove {name}: {exc}", file=sys.stderr)
    print(f"\nFreed {gb(freed)}.")
    print("The system keeps working — it falls back to DEMO mode and says so "
          "in the UI. Re-download later with: python scripts/fetch_models.py")
    print("\nTo also remove the ML libraries (~3 GB):")
    print("    pip uninstall -y torch transformers accelerate sentencepiece")
    print("Or simply delete the whole virtualenv: rm -rf .venv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
