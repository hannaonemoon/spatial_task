# -*- coding: utf-8 -*-
"""
scoring.py
====================================================================
Spatial scoring utilities.

Given (a) where the participant clicked and (b) the correct location,
compute a full set of error measures. Everything here is pure math on
NORMALIZED coordinates in [0, 1] with origin at the TOP-LEFT of the
image (the same convention used by coordinates.csv and by image
pixels), so the functions are independent of PsychoPy's screen units.

The trial code is responsible for converting a screen-pixel mouse
click into normalized image coordinates (see ui.click_to_norm); this
module then produces the numbers stored in the data file.

NONE of these values are ever shown to the participant.
====================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict


@dataclass
class ErrorMeasures:
    """All error metrics for one localization response."""
    click_norm_x: float          # click, normalized [0,1], top-left origin
    click_norm_y: float
    correct_norm_x: float        # correct location, normalized
    correct_norm_y: float
    click_px_x: float            # click in SOURCE-IMAGE pixels
    click_px_y: float
    correct_px_x: float          # correct in source-image pixels
    correct_px_y: float
    err_norm_x: float            # signed horizontal error (norm), click - correct
    err_norm_y: float            # signed vertical error (norm)
    err_norm_euclidean: float    # Euclidean distance (norm)
    err_px_x: float              # signed horizontal error (source pixels)
    err_px_y: float              # signed vertical error (source pixels)
    err_px_euclidean: float      # Euclidean distance (source pixels)
    pct_of_diagonal: float       # Euclidean error as % of image diagonal

    def as_row(self, prefix: str) -> dict:
        """Flatten to a dict with keys prefixed (e.g. 'floor_' / 'room_')."""
        return {f"{prefix}{k}": v for k, v in asdict(self).items()}


def score(click_norm: tuple[float, float],
          correct_norm: tuple[float, float],
          image_px: tuple[int, int]) -> ErrorMeasures:
    """
    Compute error measures for a single response.

    Parameters
    ----------
    click_norm   : (x, y) participant click, normalized [0,1], top-left origin.
    correct_norm : (x, y) correct location, normalized [0,1], top-left origin.
    image_px     : (width, height) of the SOURCE image in pixels; used to
                   express errors in image-pixel units and as % of diagonal.

    Returns
    -------
    ErrorMeasures dataclass (see fields above).
    """
    cx, cy = click_norm
    tx, ty = correct_norm
    w, h = image_px

    err_nx = cx - tx
    err_ny = cy - ty
    err_neuc = math.hypot(err_nx, err_ny)

    click_px = (cx * w, cy * h)
    correct_px = (tx * w, ty * h)
    err_px_x = click_px[0] - correct_px[0]
    err_px_y = click_px[1] - correct_px[1]
    err_px_euc = math.hypot(err_px_x, err_px_y)

    diag_px = math.hypot(w, h)
    pct = (err_px_euc / diag_px * 100.0) if diag_px else float("nan")

    return ErrorMeasures(
        click_norm_x=cx, click_norm_y=cy,
        correct_norm_x=tx, correct_norm_y=ty,
        click_px_x=click_px[0], click_px_y=click_px[1],
        correct_px_x=correct_px[0], correct_px_y=correct_px[1],
        err_norm_x=err_nx, err_norm_y=err_ny, err_norm_euclidean=err_neuc,
        err_px_x=err_px_x, err_px_y=err_px_y, err_px_euclidean=err_px_euc,
        pct_of_diagonal=pct,
    )
