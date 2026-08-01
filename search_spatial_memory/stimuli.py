# -*- coding: utf-8 -*-
"""
stimuli.py
====================================================================
Stimulus + answer-key loading, validation, and (optional) preloading.

Responsibilities:
  * read data/coordinates.csv (correct locations, produced by the
    preprocessing step) and data/metadata.csv (artwork_type etc.);
  * join them into a list of `ArtworkSpec` records;
  * validate that every referenced image file exists and every
    coordinate is present and in range, failing with a clear message;
  * optionally preload PsychoPy ImageStim objects for speed.

The PsychoPy experiment loads ONLY these generated CSVs -- it never
looks at the original PowerPoint or hard-codes any correct location.
====================================================================
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from . import config


@dataclass
class ArtworkSpec:
    """Everything needed to run one trial for one artwork."""
    artwork_id: str
    artwork_name: str                 # real name (from codekey.csv), e.g. 'Argote_2of6'
    artwork_type: str                 # optional: 'painting'/'sculpture' or ''
    artist: str
    title: str
    room: str
    artwork_path: str                 # absolute path to cue image
    room_path: str                    # absolute path to clean-room image
    # correct normalized locations (top-left origin, [0,1]):
    floor_correct_norm: tuple[float, float]
    room_correct_norm: tuple[float, float]
    # source image sizes (px): artwork sets the cue aspect ratio; floor/room are
    # used for pixel-space error reporting:
    artwork_img_px: tuple[int, int]
    floor_img_px: tuple[int, int]
    room_img_px: tuple[int, int]


class StimulusError(RuntimeError):
    """Raised when stimulus organization or coordinates are invalid."""


def _read_csv(path: str) -> list[dict]:
    if not os.path.isfile(path):
        raise StimulusError(f"Required file not found: {path}")
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def load_specs(strict: bool = True) -> list[ArtworkSpec]:
    """
    Load and validate all artwork specs. Raises StimulusError on any problem
    when strict=True (recommended before data collection).
    """
    coords = {r["artwork_id"]: r for r in _read_csv(config.COORDINATES_CSV)}
    meta = {r["artwork_id"]: r for r in _read_csv(config.METADATA_CSV)}
    # Optional codekey (ART0xx -> real name). Missing file is non-fatal.
    codekey = {}
    if os.path.isfile(config.CODEKEY_CSV):
        codekey = {r["artwork_id"]: r.get("artwork_name", "")
                   for r in _read_csv(config.CODEKEY_CSV)}

    problems: list[str] = []
    specs: list[ArtworkSpec] = []

    for art_id, c in sorted(coords.items()):
        m = meta.get(art_id, {})
        # artwork_type is OPTIONAL: the answer boxes fully specify the scoring
        # target, and the one-time instructions cover both wall works and
        # sculptures, so no per-artwork type is required. If present it is
        # carried through to the data for convenience.
        art_type = (m.get("artwork_type") or "").strip().lower()

        art_path = os.path.join(config.ARTWORK_DIR, c["artwork_file"])
        room_path = os.path.join(config.ROOM_DIR, c["room_file"])
        if not os.path.isfile(art_path):
            problems.append(f"{art_id}: artwork image missing: {art_path}")
        if not os.path.isfile(room_path):
            problems.append(f"{art_id}: room image missing: {room_path}")

        try:
            fnx, fny = float(c["floor_correct_norm_x"]), float(c["floor_correct_norm_y"])
            rnx, rny = float(c["room_correct_norm_x"]), float(c["room_correct_norm_y"])
        except (KeyError, ValueError):
            problems.append(f"{art_id}: missing/invalid normalized coordinates.")
            continue
        for name, v in (("floor_x", fnx), ("floor_y", fny), ("room_x", rnx), ("room_y", rny)):
            if not (0.0 <= v <= 1.0):
                problems.append(f"{art_id}: {name} out of range [0,1]: {v}")

        specs.append(ArtworkSpec(
            artwork_id=art_id,
            artwork_name=codekey.get(art_id, ""),
            artwork_type=art_type,
            artist=m.get("artist", ""),
            title=m.get("title", ""),
            room=m.get("room", ""),
            artwork_path=art_path,
            room_path=room_path,
            floor_correct_norm=(fnx, fny),
            room_correct_norm=(rnx, rny),
            artwork_img_px=(int(c.get("artwork_img_w", 0)), int(c.get("artwork_img_h", 0))),
            floor_img_px=(int(c["floor_img_w"]), int(c["floor_img_h"])),
            room_img_px=(int(c["room_img_w"]), int(c["room_img_h"])),
        ))

    if len(specs) != config.N_TRIALS:
        problems.append(f"Expected {config.N_TRIALS} artworks, found {len(specs)}.")

    if problems and strict:
        raise StimulusError("Stimulus validation failed:\n  - " + "\n  - ".join(problems))
    if problems:
        for p in problems:
            print("[stimuli][WARN]", p)
    return specs


def floorplan_path() -> str:
    """Return the single floorplan image path (any supported extension)."""
    for ext in (".jpeg", ".jpg", ".png"):
        p = os.path.join(config.FLOORPLAN_DIR, f"floorplan{ext}")
        if os.path.isfile(p):
            return p
    raise StimulusError(f"Floorplan image not found in {config.FLOORPLAN_DIR} "
                        f"(expected floorplan.jpeg/.jpg/.png).")


def load_floorplan_labels() -> list[dict]:
    """
    Load START/END/projection overlay labels, if present. Returns a list of
    {text, color_hex, norm_x, norm_y}. Missing file -> empty list (non-fatal).
    """
    path = config.FLOORPLAN_LABELS_CSV
    if not os.path.isfile(path):
        return []
    out = []
    for r in _read_csv(path):
        out.append(dict(text=r["text"], color_hex=r["color_hex"],
                        norm_x=float(r["norm_x"]), norm_y=float(r["norm_y"]),
                        # rotation/height are optional for backward compatibility
                        rotation_deg=float(r.get("rotation_deg", 0) or 0),
                        height_frac=float(r.get("height_frac", 0) or 0)))
    return out
