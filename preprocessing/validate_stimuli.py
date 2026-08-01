#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_stimuli.py
====================================================================
Pre-flight validator for the CAPTURE spatial-memory experiment.

Run this AFTER preprocessing and BEFORE collecting data. It checks
that the stimulus organization and coordinate files are complete and
internally consistent, and prints a clear pass/fail report. Exit code
is 0 if there are no ERRORS (warnings are allowed), 1 otherwise -- so
it can also gate an automated setup.

Standard library only (uses the stdlib image-size reader from
extract_from_pptx.py). No PsychoPy required.

Usage:
    python preprocessing/validate_stimuli.py
    python preprocessing/validate_stimuli.py --project /path/to/project
====================================================================
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import sys

# Reuse the stdlib PNG/JPEG size reader from the extractor (same folder).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_from_pptx import image_size          # noqa: E402

N_TRIALS = 48
REQUIRED_COORD_COLS = [
    "artwork_id", "artwork_file", "room_file",
    "floor_img_w", "floor_img_h",
    "floor_correct_norm_x", "floor_correct_norm_y",
    "room_img_w", "room_img_h",
    "room_correct_norm_x", "room_correct_norm_y",
]


class Report:
    """Collects errors + warnings and prints a tidy summary."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def error(self, m): self.errors.append(m)
    def warn(self, m): self.warnings.append(m)
    def note(self, m): self.info.append(m)

    def summarize(self) -> int:
        print("\n=== Stimulus validation report ===")
        for m in self.info:
            print(f"  [ok]   {m}")
        for m in self.warnings:
            print(f"  [WARN] {m}")
        for m in self.errors:
            print(f"  [FAIL] {m}")
        print("----------------------------------")
        if self.errors:
            print(f"RESULT: FAILED — {len(self.errors)} error(s), "
                  f"{len(self.warnings)} warning(s).")
            return 1
        print(f"RESULT: PASSED — {len(self.warnings)} warning(s).")
        return 0


def _resolve(project: str):
    return dict(
        coordinates=os.path.join(project, "data", "coordinates.csv"),
        metadata=os.path.join(project, "data", "metadata.csv"),
        codekey=os.path.join(project, "data", "codekey.csv"),
        artworks=os.path.join(project, "stimuli", "artworks"),
        rooms=os.path.join(project, "stimuli", "room_clean"),
        floorplan_dir=os.path.join(project, "stimuli", "floorplan"),
    )


def validate(project: str) -> int:
    r = Report()
    P = _resolve(project)

    # ---- coordinates.csv --------------------------------------------------
    if not os.path.isfile(P["coordinates"]):
        r.error(f"Missing coordinates file: {P['coordinates']}")
        return r.summarize()
    with open(P["coordinates"], newline="") as fh:
        rows = list(csv.DictReader(fh))

    missing_cols = [c for c in REQUIRED_COORD_COLS if c not in (rows[0] if rows else {})]
    if missing_cols:
        r.error(f"coordinates.csv missing columns: {missing_cols}")
        return r.summarize()

    if len(rows) != N_TRIALS:
        r.error(f"coordinates.csv has {len(rows)} rows; expected {N_TRIALS}.")
    ids = [row["artwork_id"] for row in rows]
    if len(set(ids)) != len(ids):
        dupes = sorted({x for x in ids if ids.count(x) > 1})
        r.error(f"Duplicate artwork_id(s) in coordinates.csv: {dupes}")
    else:
        r.note(f"coordinates.csv: {len(rows)} unique artworks.")

    # ---- floorplan image --------------------------------------------------
    fp = None
    for ext in (".jpeg", ".jpg", ".png"):
        cand = os.path.join(P["floorplan_dir"], f"floorplan{ext}")
        if os.path.isfile(cand):
            fp = cand
            break
    if fp is None:
        r.error(f"Floorplan image not found in {P['floorplan_dir']} (floorplan.jpeg/.jpg/.png).")
    else:
        r.note(f"floorplan: {os.path.basename(fp)} ({'x'.join(map(str, image_size(fp)))}).")

    # ---- per-artwork checks ----------------------------------------------
    n_flagged = 0
    for row in rows:
        aid = row["artwork_id"]
        art = os.path.join(P["artworks"], row["artwork_file"])
        room = os.path.join(P["rooms"], row["room_file"])
        if not os.path.isfile(art):
            r.error(f"{aid}: artwork image missing: {art}")
        if not os.path.isfile(room):
            r.error(f"{aid}: room image missing: {room}")

        # coordinate range
        try:
            vals = {k: float(row[k]) for k in
                    ("floor_correct_norm_x", "floor_correct_norm_y",
                     "room_correct_norm_x", "room_correct_norm_y")}
        except (ValueError, KeyError):
            r.error(f"{aid}: missing/invalid normalized coordinates.")
            continue
        for k, v in vals.items():
            if not (0.0 <= v <= 1.0):
                r.error(f"{aid}: {k}={v} out of range [0,1].")

        # recorded vs actual room image size (catches stale coordinates.csv)
        if os.path.isfile(room):
            try:
                aw, ah = image_size(room)
                if int(row["room_img_w"]) != aw or int(row["room_img_h"]) != ah:
                    r.warn(f"{aid}: room image size {aw}x{ah} != recorded "
                           f"{row['room_img_w']}x{row['room_img_h']} "
                           f"(coordinates.csv may be stale).")
            except Exception as exc:
                r.warn(f"{aid}: could not read room image size: {exc}")

        if str(row.get("flagged", "0")) not in ("0", ""):
            n_flagged += 1

    if n_flagged:
        r.warn(f"{n_flagged} artwork(s) flagged during extraction "
               f"(out-of-bounds centroid). Review diagnostics/ overlays.")

    # ---- orphan files (in folders but not referenced) --------------------
    for folder, col in ((P["artworks"], "artwork_file"), (P["rooms"], "room_file")):
        referenced = {row[col] for row in rows}
        for f in glob.glob(os.path.join(folder, "*")):
            if os.path.basename(f) not in referenced and not os.path.basename(f).startswith("."):
                r.warn(f"Unreferenced file in {os.path.basename(folder)}/: {os.path.basename(f)}")

    # ---- metadata.csv (optional artwork_type) ----------------------------
    if os.path.isfile(P["metadata"]):
        with open(P["metadata"], newline="") as fh:
            meta = list(csv.DictReader(fh))
        types = {m["artwork_id"]: (m.get("artwork_type") or "").strip().lower() for m in meta}
        bad = [k for k, v in types.items() if v not in ("", "painting", "sculpture")]
        if bad:
            r.warn(f"metadata.csv: artwork_type should be blank/'painting'/'sculpture'; "
                   f"odd values for {bad}.")
        filled = sum(1 for v in types.values() if v)
        r.note(f"metadata.csv present ({filled}/{len(types)} artwork_type filled; optional).")
    else:
        r.warn("metadata.csv not found (optional; artwork_type is not required).")

    # ---- codekey.csv (optional name map) ---------------------------------
    if os.path.isfile(P["codekey"]):
        with open(P["codekey"], newline="") as fh:
            ck = list(csv.DictReader(fh))
        names = [c.get("artwork_name", "") for c in ck]
        ck_ids = {c["artwork_id"] for c in ck}
        if len(set(names)) != len(names):
            r.warn("codekey.csv has duplicate artwork_name values.")
        missing = set(ids) - ck_ids
        if missing:
            r.warn(f"codekey.csv missing entries for: {sorted(missing)}")
        else:
            r.note(f"codekey.csv present ({len(ck)} name mappings).")
    else:
        r.warn("codekey.csv not found (optional; ART-id -> name map).")

    return r.summarize()


def main(argv=None):
    default_project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Validate CAPTURE stimulus organization.")
    ap.add_argument("--project", default=default_project,
                    help="Project root (contains stimuli/ and data/).")
    args = ap.parse_args(argv)
    sys.exit(validate(args.project))


if __name__ == "__main__":
    main()
