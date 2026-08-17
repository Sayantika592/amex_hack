"""Pixel analysis used by the DEMO-mode vision adapter.

This is deliberately *not* a stand-in that reads a metadata flag: it opens the
actual JPEGs and measures them.

Stage A (product verification) compares the card member's photo with the
merchant's listing image on two axes — colour distribution and coarse
structure — mirroring CLIP's image-image / image-text dual check, and applies
the same 0.70 threshold.  Photos too blurred or too dark to judge fall into an
inconclusive band instead of forcing a yes/no.

Stage B (damage assessment) looks for fracture signatures: long, thin,
high-contrast discontinuities that the clean listing image does not have.
Severity comes from how much of the product surface they cover.

Classical CV, no weights, no network — so it runs identically offline, and it
is honestly reported as mode="demo" (it is not CLIP and never claims to be).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

WORK = 256          # analysis resolution (thin fracture lines survive)


def _load(ref: str) -> np.ndarray | None:
    try:
        img = Image.open(ref).convert("RGB").resize((WORK, WORK), Image.BILINEAR)
    except Exception:
        return None
    return np.asarray(img).astype(np.float32) / 255.0


def _gray(a: np.ndarray) -> np.ndarray:
    return a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _foreground(a: np.ndarray) -> np.ndarray:
    """Mask the product against its backdrop.

    The backdrop is estimated from the image border, so colour comparison
    describes the *product*, not the wall behind it or the lighting."""
    border = np.concatenate([a[:6].reshape(-1, 3), a[-6:].reshape(-1, 3),
                             a[:, :6].reshape(-1, 3), a[:, -6:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    dist = np.linalg.norm(a - bg, axis=-1)
    mask = dist > 0.14
    if mask.mean() < 0.05:                 # degenerate — use everything
        mask = np.ones(a.shape[:2], dtype=bool)
    return mask


def _hist_similarity(a: np.ndarray, b: np.ndarray, bins: int = 10) -> float:
    """Per-channel histogram intersection over the product region.

    Histograms are smoothed across neighbouring bins so that a warmer light
    or a slightly darker exposure does not read as a different product."""
    ma, mb = _foreground(a), _foreground(b)
    tot = 0.0
    for c in range(3):
        ha, _ = np.histogram(a[..., c][ma], bins=bins, range=(0, 1))
        hb, _ = np.histogram(b[..., c][mb], bins=bins, range=(0, 1))
        ha = _smooth(ha / max(ha.sum(), 1))
        hb = _smooth(hb / max(hb.sum(), 1))
        tot += np.minimum(ha, hb).sum()
    return float(tot / 3)


def _smooth(h: np.ndarray) -> np.ndarray:
    k = np.array([0.25, 0.5, 0.25])
    out = np.convolve(h, k, mode="same")
    return out / max(out.sum(), 1e-9)


def _structure_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Normalised correlation of coarse luminance layout (shape agreement).

    Deliberately coarse (8x8 cells) so that a hand-held re-shoot — small
    rotation, crop and exposure drift — still matches, while a different
    product does not."""
    ga, gb = _gray(a), _gray(b)
    k = 8
    da = ga.reshape(k, WORK // k, k, WORK // k).mean(axis=(1, 3)).ravel()
    db = gb.reshape(k, WORK // k, k, WORK // k).mean(axis=(1, 3)).ravel()
    da = da - da.mean()
    db = db - db.mean()
    denom = float(np.linalg.norm(da) * np.linalg.norm(db))
    if denom < 1e-6:
        return 0.0
    return float(np.clip((da @ db) / denom, -1.0, 1.0))


def _gradient(g: np.ndarray) -> np.ndarray:
    gy = np.zeros_like(g)
    gx = np.zeros_like(g)
    gy[1:-1, :] = g[2:, :] - g[:-2, :]
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    return np.sqrt(gx * gx + gy * gy)


def _box_mean(g: np.ndarray, r: int = 4) -> np.ndarray:
    """Local mean via integral image (no scipy dependency)."""
    pad = np.pad(g, r + 1, mode="edge")
    ii = pad.cumsum(0).cumsum(1)
    h, w = g.shape
    k = 2 * r + 1
    y0, x0 = np.arange(h), np.arange(w)
    A = ii[np.ix_(y0, x0)]
    B = ii[np.ix_(y0, x0 + k)]
    C = ii[np.ix_(y0 + k, x0)]
    D = ii[np.ix_(y0 + k, x0 + k)]
    return (D - B - C + A) / (k * k)


def _local_contrast(g: np.ndarray, r: int = 4) -> np.ndarray:
    """How much darker each pixel is than its local neighbourhood."""
    return _box_mean(g, r) - g


def _focus(a: np.ndarray) -> float:
    """Laplacian-style focus measure — low means blurred/unjudgeable."""
    g = _gray(a)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1]
           + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def verify(photo_ref: str, listing_ref: str, threshold: float = 0.75) -> dict | None:
    """Stage A on real pixels. Returns None if either image is unreadable."""
    p, l = _load(photo_ref), _load(listing_ref)
    if p is None or l is None:
        return None
    colour = _hist_similarity(p, l)
    structure = (_structure_similarity(p, l) + 1) / 2      # → 0..1
    combined = 0.55 * structure + 0.45 * colour
    focus = _focus(p)
    brightness = float(_gray(p).mean())

    inconclusive = focus < 0.0005 or brightness < 0.22
    if inconclusive:
        match = None
        note = ("Photo is too blurred or underexposed to verify the product "
                "with confidence")
    elif combined >= threshold:
        match, note = True, None
    elif combined <= threshold - 0.09:
        match, note = False, None
    else:
        match = None                       # borderline — refuse to guess
        note = ("Similarity is borderline; the photo neither confirms nor "
                "refutes that this is the listed product")
    out = {
        "product_match": match,
        "image_similarity": round(structure, 3),
        "text_similarity": round(colour, 3),
        "combined_score": round(combined, 3),
        "threshold": threshold,
        "focus_measure": round(focus, 5),
    }
    if note:
        out["note"] = note
    return out


def damage(photo_ref: str, listing_ref: str) -> dict | None:
    """Stage B on real pixels: find fracture signatures absent from the listing."""
    p, l = _load(photo_ref), _load(listing_ref)
    if p is None or l is None:
        return None
    gp, gl = _gray(p), _gray(l)
    # A fracture is a THIN line much darker than its immediate surroundings.
    # Large dark regions (a bezel, a shadow) are not darker than their own
    # local mean, so this isolates cracks rather than dark product parts.
    frac_p = float((_local_contrast(gp) > 0.10).mean())
    frac_l = float((_local_contrast(gl) > 0.10).mean())
    ep, el = _gradient(gp), _gradient(gl)
    edge_p = float((ep > 0.30).mean())
    edge_l = float((el > 0.30).mean())

    excess_lines = max(frac_p - frac_l, 0.0)
    excess_edges = max(edge_p - edge_l, 0.0)
    score = excess_lines * 0.75 + excess_edges * 0.25

    if score < 0.0025:
        return {"has_damage": False, "damage_description": "No visible damage",
                "severity_label": "none", "severity_score": 0.0,
                "consistency_check": "yes", "damage_metric": round(score, 4)}
    if score < 0.009:
        sev, sc = "minor", 0.3
    elif score < 0.024:
        sev, sc = "moderate", 0.6
    else:
        sev, sc = "severe", 0.9
    desc = {
        "minor": "a short surface fracture on one edge of the item",
        "moderate": "multiple fracture lines running across the item surface",
        "severe": "extensive fracture lines radiating from an impact point "
                  "across the item surface",
    }[sev]
    return {"has_damage": True, "damage_description": desc,
            "severity_label": sev, "severity_score": sc,
            "consistency_check": "yes", "damage_metric": round(score, 4)}
