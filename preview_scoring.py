#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preview_scoring.py
====================================================================
Inspect the spatial scoring WITHOUT running the experiment or clicking
through 48 trials. Prints worked examples of what gets computed and
saved for each click.

Two things to know:
  * Scoring is REAL-TIME in the experiment: `scoring.score()` runs the
    instant a click is registered (see search_spatial_memory/trial.py),
    and the result is written to the per-trial CSV. It is never shown
    to the participant.
  * To *watch* it live during a session, set SHOW_SCORE_FEEDBACK=True in
    config.py and run in Debug mode — after each click the correct
    location and error are drawn on screen.

This tool uses only the pure-math scoring module (no PsychoPy needed).

Usage:
    python preview_scoring.py                # demo on the first artwork
    python preview_scoring.py --artwork ART007
    python preview_scoring.py --all          # summary line for all 48
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search_spatial_memory import scoring, stimuli


def _fmt(err):
    return (f"Euclid={err.err_norm_euclidean:.4f} norm "
            f"({err.err_px_euclidean:6.1f}px, {err.pct_of_diagonal:5.2f}% diag)  "
            f"H={err.err_norm_x:+.4f} V={err.err_norm_y:+.4f}")


def demo_one(spec):
    """Show scoring for several illustrative clicks on one artwork."""
    print(f"\n=== {spec.artwork_id}"
          + (f"  ({spec.artwork_name})" if spec.artwork_name else "")
          + " ===")
    for stage, correct, size in (
            ("FLOORPLAN", spec.floor_correct_norm, spec.floor_img_px),
            ("ROOM", spec.room_correct_norm, spec.room_img_px)):
        cx, cy = correct
        print(f"\n  {stage}: correct = ({cx:.4f}, {cy:.4f}) in a {size[0]}x{size[1]} image")
        examples = [
            ("perfect click (on target)", (cx, cy)),
            ("10% of width to the right", (min(1.0, cx + 0.10), cy)),
            ("5% down + 5% left", (max(0.0, cx - 0.05), min(1.0, cy + 0.05))),
            ("opposite corner (worst case)", (1.0 - cx, 1.0 - cy)),
        ]
        for label, click in examples:
            err = scoring.score(click, correct, size)
            print(f"    click=({click[0]:.3f},{click[1]:.3f})  {label:32s} -> {_fmt(err)}")

    print("\n  Fields stored per stage in the data file (prefixed floor_/room_):")
    fields = list(vars(scoring.score((0.5, 0.5), spec.floor_correct_norm,
                                     spec.floor_img_px)).keys())
    for i in range(0, len(fields), 3):
        print("    " + ", ".join(fields[i:i + 3]))


def summary_all(specs):
    """One line per artwork: a fixed 10%-diagonal-ish offset, to show ranges."""
    print(f"\n{'id':7} {'name':16} {'floor(perfect)':>16} {'room(10% right)':>18}")
    for s in specs:
        f0 = scoring.score(s.floor_correct_norm, s.floor_correct_norm, s.floor_img_px)
        cx, cy = s.room_correct_norm
        r10 = scoring.score((min(1.0, cx + 0.10), cy), s.room_correct_norm, s.room_img_px)
        print(f"{s.artwork_id:7} {s.artwork_name[:16]:16} "
              f"{f0.pct_of_diagonal:14.2f}% {r10.pct_of_diagonal:16.2f}%")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Preview the spatial scoring.")
    ap.add_argument("--artwork", help="Artwork id to demo (default: first).")
    ap.add_argument("--all", action="store_true", help="Summary line for every artwork.")
    args = ap.parse_args(argv)

    specs = stimuli.load_specs(strict=False)
    by_id = {s.artwork_id: s for s in specs}

    print("Scoring = Euclidean distance between click and correct location, "
          "reported in normalized units, source-image pixels, and as % of the "
          "image diagonal (so floorplan and room errors are comparable).")

    if args.all:
        summary_all(specs)
    else:
        spec = by_id.get(args.artwork, specs[0])
        demo_one(spec)

    print("\n(These are simulated clicks for illustration. In a real session the "
          "click comes from the mouse and the same numbers are written to "
          "data/results/<session>.csv.)")


if __name__ == "__main__":
    main()
