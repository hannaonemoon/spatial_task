#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_floorplan_coords.py   (FALLBACK / Script 1)
====================================================================
Image-based extractor for FLOORPLAN answer-key images.

PRIMARY PATH: For this study the answer keys live as native vector
shapes inside the PowerPoint deck, and `extract_from_pptx.py` reads
their exact centroids. Prefer that -- it is more accurate and needs no
image processing.

USE THIS SCRIPT ONLY IF you instead have a folder of *flattened*
floorplan answer-key images, one per artwork, each showing the SAME
floorplan with a single RED DOT marking the correct location:

    floorplan_keys/ART001.png
    floorplan_keys/ART002.png
    ...

It detects the red dot, computes its centroid, and writes pixel +
normalized coordinates plus diagnostic overlays. Ambiguous detections
(no red / multiple red blobs / diffuse red) are FLAGGED for review.

Requires: numpy, Pillow (both ship with PsychoPy).

Usage:
    python preprocessing/extract_floorplan_coords.py \
        --keys-dir stimuli/floorplan_keys \
        --out-csv  data/floorplan_coords_fallback.csv \
        --diag-dir diagnostics/floorplan_keys
====================================================================
"""

from __future__ import annotations

import argparse
import csv
import glob
import os

import numpy as np
from PIL import Image, ImageDraw


# --------------------------------------------------------------------------
# Red detection
# --------------------------------------------------------------------------

def red_mask(rgb: np.ndarray,
             r_min: int = 110, dominance: int = 55) -> np.ndarray:
    """
    Boolean mask of 'red' pixels: red channel high AND clearly dominant over
    green and blue. Works for pure red (#FF0000) and crimson dot markers.
    """
    r = rgb[:, :, 0].astype(int)
    g = rgb[:, :, 1].astype(int)
    b = rgb[:, :, 2].astype(int)
    return (r >= r_min) & (r - g >= dominance) & (r - b >= dominance)


def largest_blob(mask: np.ndarray):
    """
    Return (mask_of_largest_component, n_components) using a simple stdlib
    flood fill (avoids a scipy/opencv dependency). Good enough for a handful
    of red blobs per image.
    """
    visited = np.zeros_like(mask, dtype=bool)
    best = None
    best_size = 0
    n_components = 0
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    seeds = set(zip(ys.tolist(), xs.tolist()))
    seen = set()
    for sy, sx in list(seeds):
        if (sy, sx) in seen:
            continue
        # BFS over 4-connectivity
        stack = [(sy, sx)]
        comp = []
        while stack:
            y, x = stack.pop()
            if y < 0 or y >= h or x < 0 or x >= w:
                continue
            if (y, x) in seen or not mask[y, x]:
                continue
            seen.add((y, x))
            comp.append((y, x))
            stack.extend([(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)])
        if comp:
            n_components += 1
            if len(comp) > best_size:
                best_size = len(comp)
                best = comp
    out = np.zeros_like(mask, dtype=bool)
    if best:
        for y, x in best:
            out[y, x] = True
    return out, n_components


# --------------------------------------------------------------------------
# Per-image detection
# --------------------------------------------------------------------------

def detect_dot(path: str, min_pixels: int = 20):
    """
    Detect the red dot in one floorplan key image.

    Returns dict with pixel/normalized centroid and a `flag` string
    ('' if clean, otherwise the reason it is suspect).
    """
    im = Image.open(path).convert("RGB")
    rgb = np.asarray(im)
    h, w = rgb.shape[:2]
    mask = red_mask(rgb)
    n_red = int(mask.sum())

    flag = ""
    if n_red < min_pixels:
        flag = f"too-few-red-pixels({n_red})"
        return dict(w=w, h=h, cx=float("nan"), cy=float("nan"),
                    nx=float("nan"), ny=float("nan"), n_red=n_red,
                    n_blobs=0, flag=flag)

    blob, n_blobs = largest_blob(mask)
    ys, xs = np.nonzero(blob)
    cy = float(ys.mean())
    cx = float(xs.mean())

    # Ambiguity checks: multiple blobs, or the blob is not compact (diffuse).
    bbox_h = ys.max() - ys.min() + 1
    bbox_w = xs.max() - xs.min() + 1
    diffuse = max(bbox_w, bbox_h) > 0.15 * max(w, h)
    if n_blobs > 1:
        flag = f"multiple-red-blobs({n_blobs})"
    elif diffuse:
        flag = "diffuse-red-region"

    return dict(w=w, h=h, cx=round(cx, 2), cy=round(cy, 2),
                nx=round(cx / w, 6), ny=round(cy / h, 6),
                n_red=n_red, n_blobs=n_blobs, flag=flag)


def save_overlay(path: str, out_path: str, det: dict):
    """Draw the detected centroid on a copy of the image for visual QC."""
    im = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(im)
    if det["cx"] == det["cx"]:                     # not NaN
        x, y = det["cx"], det["cy"]
        r = max(6, int(0.01 * max(im.size)))
        draw.ellipse([x - r, y - r, x + r, y + r], outline=(0, 200, 255), width=3)
        draw.line([x - r, y, x + r, y], fill=(0, 200, 255), width=2)
        draw.line([x, y - r, x, y + r], fill=(0, 200, 255), width=2)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect red dots in floorplan answer-key images.")
    ap.add_argument("--keys-dir", required=True, help="Folder of floorplan key images (ART###.*).")
    ap.add_argument("--out-csv", required=True, help="Output CSV path.")
    ap.add_argument("--diag-dir", default=None, help="Folder for diagnostic overlays (optional).")
    args = ap.parse_args(argv)

    files = sorted(glob.glob(os.path.join(args.keys_dir, "*")))
    files = [f for f in files if os.path.splitext(f)[1].lower() in (".png", ".jpg", ".jpeg")]
    if not files:
        raise SystemExit(f"No key images found in {args.keys_dir}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out_csv)), exist_ok=True)
    rows, flagged = [], []
    for f in files:
        art_id = os.path.splitext(os.path.basename(f))[0]
        det = detect_dot(f)
        rows.append(dict(artwork_id=art_id, floor_img_w=det["w"], floor_img_h=det["h"],
                         floor_correct_px_x=det["cx"], floor_correct_px_y=det["cy"],
                         floor_correct_norm_x=det["nx"], floor_correct_norm_y=det["ny"],
                         n_red=det["n_red"], n_blobs=det["n_blobs"], flag=det["flag"]))
        if det["flag"]:
            flagged.append((art_id, det["flag"]))
        if args.diag_dir:
            save_overlay(f, os.path.join(args.diag_dir, f"{art_id}.png"), det)

    with open(args.out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"[floorplan-keys] processed {len(rows)} images -> {args.out_csv}")
    if args.diag_dir:
        print(f"[floorplan-keys] overlays -> {args.diag_dir}/")
    if flagged:
        print(f"[floorplan-keys] FLAGGED {len(flagged)} image(s) for review:")
        for aid, why in flagged:
            print(f"    {aid}: {why}")
    else:
        print("[floorplan-keys] no flags — all detections look clean.")


if __name__ == "__main__":
    main()
