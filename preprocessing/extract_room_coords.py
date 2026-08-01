#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_room_coords.py   (FALLBACK / Script 2)
====================================================================
Image-based extractor for ROOM answer-key images.

PRIMARY PATH: The room answer keys live as native vector shapes (a red
bounding box drawn as line segments) inside the PowerPoint deck, and
`extract_from_pptx.py` reads the exact box centroid. Prefer that.

USE THIS SCRIPT ONLY IF you instead have a folder of *flattened* room
answer-key images, one per artwork, each showing the room with a RED
BOUNDING BOX marking the artwork's location:

    room_keys/ART001.png
    room_keys/ART002.png
    ...

It detects the red box (whether drawn as an outline or filled),
computes the CENTROID of the box, and writes pixel + normalized
coordinates plus diagnostic overlays. Failed detections (no red / red
scattered across the image) are FLAGGED for review.

Requires: numpy, Pillow (both ship with PsychoPy).

Usage:
    python preprocessing/extract_room_coords.py \
        --keys-dir stimuli/room_keys \
        --out-csv  data/room_coords_fallback.csv \
        --diag-dir diagnostics/room_keys
====================================================================
"""

from __future__ import annotations

import argparse
import csv
import glob
import os

import numpy as np
from PIL import Image, ImageDraw


def red_mask(rgb: np.ndarray, r_min: int = 110, dominance: int = 55) -> np.ndarray:
    """Boolean mask of clearly-red pixels (see extract_floorplan_coords)."""
    r = rgb[:, :, 0].astype(int)
    g = rgb[:, :, 1].astype(int)
    b = rgb[:, :, 2].astype(int)
    return (r >= r_min) & (r - g >= dominance) & (r - b >= dominance)


def detect_box(path: str, min_pixels: int = 40):
    """
    Detect the red bounding box in one room key image and return its centroid.

    The centroid is the middle of the red pixels' bounding rectangle, which is
    correct whether the box is an outline (4 lines) or a filled rectangle. A
    robustness check flags cases where the red pixels are scattered (which
    would make the bounding box meaningless).
    """
    im = Image.open(path).convert("RGB")
    rgb = np.asarray(im)
    h, w = rgb.shape[:2]
    mask = red_mask(rgb)
    n_red = int(mask.sum())

    if n_red < min_pixels:
        return dict(w=w, h=h, cx=float("nan"), cy=float("nan"),
                    nx=float("nan"), ny=float("nan"),
                    bx0=float("nan"), by0=float("nan"), bx1=float("nan"), by1=float("nan"),
                    n_red=n_red, flag=f"too-few-red-pixels({n_red})")

    ys, xs = np.nonzero(mask)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0

    # Scatter check: for a clean box (outline or filled), red pixels should sit
    # ON the rectangle's perimeter/area. If the filled fraction of the bounding
    # box is implausibly low AND the box is large, the red is likely scattered.
    box_area = max(1, (x1 - x0 + 1) * (y1 - y0 + 1))
    fill_frac = n_red / box_area
    flag = ""
    if fill_frac < 0.01 and box_area > 0.5 * w * h:
        flag = f"scattered-red(fill={fill_frac:.3f})"

    return dict(w=w, h=h, cx=round(cx, 2), cy=round(cy, 2),
                nx=round(cx / w, 6), ny=round(cy / h, 6),
                bx0=round(x0 / w, 6), by0=round(y0 / h, 6),
                bx1=round(x1 / w, 6), by1=round(y1 / h, 6),
                n_red=n_red, flag=flag)


def save_overlay(path: str, out_path: str, det: dict):
    im = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(im)
    if det["cx"] == det["cx"]:                     # not NaN
        w, h = im.size
        draw.rectangle([det["bx0"] * w, det["by0"] * h, det["bx1"] * w, det["by1"] * h],
                       outline=(0, 200, 255), width=3)
        x, y = det["cx"], det["cy"]
        r = max(6, int(0.012 * max(im.size)))
        draw.line([x - r, y, x + r, y], fill=(0, 200, 255), width=2)
        draw.line([x, y - r, x, y + r], fill=(0, 200, 255), width=2)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect red bounding boxes in room answer-key images.")
    ap.add_argument("--keys-dir", required=True, help="Folder of room key images (ART###.*).")
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
        det = detect_box(f)
        rows.append(dict(artwork_id=art_id, room_img_w=det["w"], room_img_h=det["h"],
                         room_correct_px_x=det["cx"], room_correct_px_y=det["cy"],
                         room_correct_norm_x=det["nx"], room_correct_norm_y=det["ny"],
                         room_box_norm_x0=det["bx0"], room_box_norm_y0=det["by0"],
                         room_box_norm_x1=det["bx1"], room_box_norm_y1=det["by1"],
                         n_red=det["n_red"], flag=det["flag"]))
        if det["flag"]:
            flagged.append((art_id, det["flag"]))
        if args.diag_dir:
            save_overlay(f, os.path.join(args.diag_dir, f"{art_id}.png"), det)

    with open(args.out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"[room-keys] processed {len(rows)} images -> {args.out_csv}")
    if args.diag_dir:
        print(f"[room-keys] overlays -> {args.diag_dir}/")
    if flagged:
        print(f"[room-keys] FLAGGED {len(flagged)} image(s) for review:")
        for aid, why in flagged:
            print(f"    {aid}: {why}")
    else:
        print("[room-keys] no flags — all detections look clean.")


if __name__ == "__main__":
    main()
