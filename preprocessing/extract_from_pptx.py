#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_from_pptx.py
====================================================================
AUTHORITATIVE stimulus + answer-key extractor for the CAPTURE spatial
memory experiment.

The stimuli for this study were authored as a single PowerPoint deck in
which every artwork occupies a block of 4 consecutive slides:

    slide 4*(t-1)+1 : artwork image  +  museum floorplan  +  red DOT
                      (the red dot marks the correct floorplan location)
    slide 4*(t-1)+2 : the room WITH the artwork present   (NOT used)
    slide 4*(t-1)+3 : the room with the artwork REMOVED    (subject sees this)
    slide 4*(t-1)+4 : the same removed-art room  +  red BOUNDING BOX
                      (the box marks the correct in-room location)

Crucially, the red markers are *native PowerPoint vector shapes*, not
pixels burned into the images:

  * the floorplan marker is a red circle IMAGE placed on top of the
    (clean) floorplan image;
  * the room marker is a rectangle drawn as FOUR red line shapes.

That means we can read the marker geometry directly from the slide XML
and compute exact, sub-pixel centroids -- far more reliable than trying
to detect red blobs in a rendered bitmap. This script does exactly that.

It requires ONLY the Python standard library (no Pillow / numpy / opencv),
so it runs anywhere. For an image-based fallback (used only if you ever
export flattened answer-key PNGs instead of using this deck), see
`extract_floorplan_coords.py` and `extract_room_coords.py`.

--------------------------------------------------------------------
OUTPUTS (written under the project root, next to `stimuli/`):

  stimuli/artworks/ART001.<ext> ... ART048.<ext>   (cue images)
  stimuli/room_clean/ART001.<ext> ... ART048.<ext> (art-removed rooms)
  stimuli/floorplan/floorplan.<ext>                (single clean floorplan)
  stimuli/floorplan/floorplan_labels.csv           (START/END/... overlays)
  data/coordinates.csv                             (correct locations)
  data/metadata_template.csv                       (fill in artwork_type)
  diagnostics/floorplan_overlays.html              (visual QC)
  diagnostics/room_overlays.html                   (visual QC)

Run:
    python3 preprocessing/extract_from_pptx.py \
        --pptx "/path/to/CAPTURE Stimuli-2.pptx" \
        --out  "/path/to/CAPTURE_spatial_memory_test"

If --pptx / --out are omitted the script uses the defaults below.
====================================================================
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import os
import shutil
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Configuration / constants
# --------------------------------------------------------------------------

N_TRIALS = 48
SLIDES_PER_TRIAL = 4

# OpenXML namespaces. We deliberately compare by *local* tag name in most of
# the code (robust against namespace-prefix quirks), but keep the relationship
# namespace handy for reading r:embed attributes.
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Fills used by the deck. The floorplan slides reuse one floorplan image and
# one red-dot image across every trial; we identify them by content hash at
# runtime rather than hard-coding, but the red bounding-box color is a stable
# pure red.
RED_HEX = "FF0000"           # room bounding-box lines
DEFAULT_PPTX = os.path.expanduser("~/Downloads/CAPTURE Stimuli-2.pptx")
DEFAULT_OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------
# Small stdlib image-dimension reader (PNG + JPEG). Avoids a Pillow dependency
# just to learn width/height so we can convert normalized coords -> pixels.
# --------------------------------------------------------------------------

def image_size(path: str) -> tuple[int, int]:
    """Return (width, height) in pixels for a PNG or JPEG file, stdlib only."""
    with open(path, "rb") as fh:
        head = fh.read(26)
        # PNG: 8-byte signature, then IHDR chunk with width/height big-endian.
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", head[16:24])
            return int(w), int(h)
        # JPEG: walk the marker segments until a Start-Of-Frame (SOFn).
        if head[:2] == b"\xff\xd8":
            fh.seek(2)
            while True:
                b = fh.read(1)
                while b and b != b"\xff":
                    b = fh.read(1)
                marker = fh.read(1)
                while marker == b"\xff":            # skip fill bytes
                    marker = fh.read(1)
                if not marker:
                    break
                m = marker[0]
                # SOF0..SOF15 except DHT(0xC4)/JPG(0xC8)/DAC(0xCC) carry size.
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    fh.read(3)                       # length(2)+precision(1)
                    h, w = struct.unpack(">HH", fh.read(4))
                    return int(w), int(h)
                seg_len = struct.unpack(">H", fh.read(2))[0]
                fh.seek(seg_len - 2, os.SEEK_CUR)
    raise ValueError(f"Unsupported / unreadable image: {path}")


# --------------------------------------------------------------------------
# PPTX geometry model
# --------------------------------------------------------------------------

def _ln(el) -> str:
    """Local (namespace-stripped) tag name of an element."""
    return el.tag.split("}")[-1]


def _child(el, name):
    for c in el:
        if _ln(c) == name:
            return c
    return None


def _descendant(el, name):
    for c in el.iter():
        if _ln(c) == name:
            return c
    return None


@dataclass
class Shape:
    """A resolved shape: image/autoshape flattened into absolute slide EMU."""
    kind: str                       # 'sp' or 'pic'
    prst: str                       # preset geometry (e.g. 'line', 'rect', '')
    rect: tuple[float, float, float, float]   # (x0, y0, x1, y1) in slide EMU
    fills: list[str] = field(default_factory=list)     # srgbClr hex values
    embed: str | None = None        # r:embed id of an image, if any
    media: str | None = None        # resolved media filename, if any

    @property
    def cx(self) -> float:
        return (self.rect[0] + self.rect[2]) / 2.0

    @property
    def cy(self) -> float:
        return (self.rect[1] + self.rect[3]) / 2.0


class Deck:
    """Thin reader over an unzipped-in-memory .pptx."""

    def __init__(self, pptx_path: str):
        self.path = pptx_path
        self.zip = zipfile.ZipFile(pptx_path, "r")
        # Map media basename -> content hash, for identifying reused images.
        self._media_hash: dict[str, str] = {}
        for name in self.zip.namelist():
            if name.startswith("ppt/media/"):
                data = self.zip.read(name)
                self._media_hash[os.path.basename(name)] = hashlib.md5(data).hexdigest()[:12]

    # ---- relationship + media helpers ------------------------------------

    def _rels(self, slide_no: int) -> dict[str, str]:
        rp = f"ppt/slides/_rels/slide{slide_no}.xml.rels"
        out: dict[str, str] = {}
        try:
            root = ET.fromstring(self.zip.read(rp))
        except KeyError:
            return out
        for r in root:
            out[r.get("Id")] = os.path.basename(r.get("Target"))
        return out

    def media_bytes(self, filename: str) -> bytes:
        return self.zip.read(f"ppt/media/{filename}")

    def media_hash(self, filename: str | None) -> str | None:
        return self._media_hash.get(filename) if filename else None

    # ---- geometry resolution --------------------------------------------

    @staticmethod
    def _xfrm(el):
        """Find the a:xfrm for a shape (spPr) or group (grpSpPr)."""
        for pr in ("spPr", "grpSpPr"):
            p = _child(el, pr)
            if p is not None:
                xf = _child(p, "xfrm")
                if xf is not None:
                    return xf
        return None

    def _walk(self, el, tf, rels, out: list[Shape]):
        """
        Recursively flatten a shape tree into absolute-EMU `Shape`s.

        `tf(x, y) -> (X, Y)` maps a coordinate in the current (possibly nested
        group) coordinate space to absolute slide EMU. Group transforms compose
        the child-offset/child-extent (chOff/chExt) -> offset/extent (off/ext)
        mapping, exactly as PowerPoint does.
        """
        for c in el:
            tag = _ln(c)
            if tag == "grpSp":
                xf = self._xfrm(c)
                if xf is None:
                    self._walk(c, tf, rels, out)
                    continue
                off, ext = _child(xf, "off"), _child(xf, "ext")
                choff, chext = _child(xf, "chOff"), _child(xf, "chExt")
                ox, oy = int(off.get("x")), int(off.get("y"))
                ex, ey = int(ext.get("cx")), int(ext.get("cy"))
                cox, coy = (int(choff.get("x")), int(choff.get("y"))) if choff is not None else (0, 0)
                cex, cey = (int(chext.get("cx")), int(chext.get("cy"))) if chext is not None else (ex, ey)
                sx = ex / cex if cex else 1.0
                sy = ey / cey if cey else 1.0

                def make(ox, oy, cox, coy, sx, sy, parent):
                    return lambda x, y: parent(ox + (x - cox) * sx, oy + (y - coy) * sy)

                self._walk(c, make(ox, oy, cox, coy, sx, sy, tf), rels, out)

            elif tag in ("sp", "pic"):
                xf = self._xfrm(c)
                if xf is None:
                    continue
                off, ext = _child(xf, "off"), _child(xf, "ext")
                if off is None or ext is None:
                    continue
                ox, oy = int(off.get("x")), int(off.get("y"))
                ex, ey = int(ext.get("cx")), int(ext.get("cy"))
                x0, y0 = tf(ox, oy)
                x1, y1 = tf(ox + ex, oy + ey)
                fills = [f.get("val") for f in c.iter() if _ln(f) == "srgbClr"]
                blip = _descendant(c, "blip")
                embed = blip.get(f"{{{NS_REL}}}embed") if blip is not None else None
                geo = _descendant(c, "prstGeom")
                prst = geo.get("prst") if geo is not None else ""
                media = rels.get(embed) if embed else None
                out.append(Shape(
                    kind=tag, prst=prst,
                    rect=(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
                    fills=fills, embed=embed, media=media))

    def shapes(self, slide_no: int) -> list[Shape]:
        root = ET.fromstring(self.zip.read(f"ppt/slides/slide{slide_no}.xml"))
        tree = _descendant(root, "spTree")
        rels = self._rels(slide_no)
        out: list[Shape] = []
        self._walk(tree, lambda x, y: (x, y), rels, out)
        return out

    def slide_texts(self, slide_no: int) -> list[dict]:
        """
        Return text-bearing shapes as dicts:
            {text, color(hex), rect(abs EMU), rot_deg, font_emu}

        `rect` is group-transform-resolved (matches image coordinates), so text
        anchors normalize correctly onto the floorplan image. `rot_deg` is the
        shape's intrinsic rotation in degrees (PowerPoint `rot`, positive =
        clockwise). `font_emu` is the run font height in EMU (for proportional
        sizing against the floorplan image).
        """
        root = ET.fromstring(self.zip.read(f"ppt/slides/slide{slide_no}.xml"))
        rels = self._rels(slide_no)
        out: list[Shape] = []
        self._walk(_descendant(root, "spTree"), lambda x, y: (x, y), rels, out)
        # Resolved 'sp' shapes in document order (matches the raw sp elements).
        sp_shapes = [s for s in out if s.kind == "sp"]

        texts = []
        idx = 0
        for c in root.iter():
            if _ln(c) != "sp":
                continue
            sh = sp_shapes[idx] if idx < len(sp_shapes) else None
            idx += 1
            runs = [t.text for t in c.iter() if _ln(t) == "t" and t.text]
            txt = "".join(runs).strip()
            if not txt or sh is None:
                continue
            # Text-run color (prefer a run's solidFill over any shape fill).
            color = ""
            rpr = _descendant(c, "rPr")
            if rpr is not None:
                sc = _descendant(rpr, "srgbClr")
                if sc is not None:
                    color = sc.get("val")
            if not color and sh.fills:
                color = sh.fills[0]
            # Font size: PowerPoint sz is hundredths of a point; 1 pt = 12700 EMU.
            font_emu = 0
            if rpr is not None and rpr.get("sz"):
                font_emu = int(rpr.get("sz")) / 100.0 * 12700.0
            # Intrinsic rotation (spPr/xfrm rot, in 60000ths of a degree).
            rot_deg = 0.0
            xf = self._xfrm(c)
            if xf is not None and xf.get("rot"):
                rot_deg = int(xf.get("rot")) / 60000.0
            texts.append(dict(text=txt, color=color or "000000", rect=sh.rect,
                              rot_deg=rot_deg, font_emu=font_emu))
        return texts


# --------------------------------------------------------------------------
# Per-trial extraction
# --------------------------------------------------------------------------

def norm_within(rect_img, cx, cy):
    """Normalize an absolute point to [0,1] within an image's absolute rect."""
    x0, y0, x1, y1 = rect_img
    return (cx - x0) / (x1 - x0), (cy - y0) / (y1 - y0)


def extract(pptx_path: str, out_root: str) -> None:
    deck = Deck(pptx_path)

    # --- Identify the reused floorplan image and red-dot image by frequency.
    # On every floorplan slide (4t+1) there are exactly three images: the
    # unique artwork, the shared floorplan, and the shared red dot. The two
    # shared images are, by definition, the ones whose content hash repeats
    # across all 48 floorplan slides.
    floor_slides = [4 * t + 1 for t in range(N_TRIALS)]
    hash_counts: dict[str, int] = {}
    for sn in floor_slides:
        seen = set()
        for s in deck.shapes(sn):
            h = deck.media_hash(s.media)
            if h and h not in seen:
                seen.add(h)
                hash_counts[h] = hash_counts.get(h, 0) + 1
    shared = sorted([h for h, c in hash_counts.items() if c >= N_TRIALS - 2])
    if len(shared) < 2:
        sys.exit("ERROR: could not identify shared floorplan/dot images. "
                 "Deck structure may differ from expectation.")

    # Distinguish floorplan (large, wide) from red dot (small, ~square) using
    # the median on-slide size of each shared hash.
    def median_area(target_hash):
        areas = []
        for sn in floor_slides:
            for s in deck.shapes(sn):
                if deck.media_hash(s.media) == target_hash:
                    areas.append((s.rect[2] - s.rect[0]) * (s.rect[3] - s.rect[1]))
        areas.sort()
        return areas[len(areas) // 2] if areas else 0

    shared.sort(key=median_area)
    dot_hash, floor_hash = shared[0], shared[-1]

    out_art = os.path.join(out_root, "stimuli", "artworks")
    out_room = os.path.join(out_root, "stimuli", "room_clean")
    out_floor = os.path.join(out_root, "stimuli", "floorplan")
    out_data = os.path.join(out_root, "data")
    out_diag = os.path.join(out_root, "diagnostics")
    for d in (out_art, out_room, out_floor, out_data, out_diag):
        os.makedirs(d, exist_ok=True)

    # --- Copy the single clean floorplan image once. -----------------------
    floor_media = None
    for s in deck.shapes(floor_slides[0]):
        if deck.media_hash(s.media) == floor_hash:
            floor_media = s.media
            break
    floor_ext = os.path.splitext(floor_media)[1].lower()
    floor_out = os.path.join(out_floor, f"floorplan{floor_ext}")
    with open(floor_out, "wb") as fh:
        fh.write(deck.media_bytes(floor_media))
    floor_w, floor_h = image_size(floor_out)

    # --- Extract the START/END/projection labels (position, rotation, and
    #     proportional font size relative to the floorplan image) so the
    #     experiment can re-draw them faithfully as overlays. ----------------
    labels_path = os.path.join(out_floor, "floorplan_labels.csv")
    # Use the floorplan image rect from slide 1 as the reference frame.
    fp_rect = next(s.rect for s in deck.shapes(floor_slides[0])
                   if deck.media_hash(s.media) == floor_hash)
    fp_h_emu = fp_rect[3] - fp_rect[1]
    with open(labels_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["text", "color_hex", "norm_x", "norm_y", "rotation_deg", "height_frac"])
        for t in deck.slide_texts(floor_slides[0]):
            rect = t["rect"]
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            nx, ny = norm_within(fp_rect, cx, cy)
            # Keep only labels that fall on the floorplan (ignore stray boxes
            # such as the artwork-title caption placed beside the floorplan).
            if -0.05 <= nx <= 1.05 and -0.05 <= ny <= 1.05:
                # height as a fraction of the floorplan image height, so the
                # label scales with the displayed floorplan on any screen.
                height_frac = (t["font_emu"] / fp_h_emu) if fp_h_emu else 0.03
                w.writerow([t["text"], t["color"], f"{nx:.5f}", f"{ny:.5f}",
                            f"{t['rot_deg']:.2f}", f"{height_frac:.5f}"])

    # --- Per-trial loop ----------------------------------------------------
    coord_rows = []
    floor_diag, room_diag = [], []

    for t in range(N_TRIALS):
        art_id = f"ART{t + 1:03d}"
        fs = 4 * t + 1            # floorplan slide
        rc = 4 * t + 3           # room-clean slide (subject sees)
        rk = 4 * t + 4           # room-key slide (red box)

        # ----- artwork image (the one shared-hash-free image on slide fs) --
        fshapes = deck.shapes(fs)
        art_shape = next(s for s in fshapes
                         if s.media and deck.media_hash(s.media) not in (floor_hash, dot_hash))
        art_ext = os.path.splitext(art_shape.media)[1].lower()
        art_out = os.path.join(out_art, f"{art_id}{art_ext}")
        with open(art_out, "wb") as fh:
            fh.write(deck.media_bytes(art_shape.media))
        art_w, art_h = image_size(art_out)

        # ----- clean room image (single image on slide rc) -----------------
        room_shape_clean = next(s for s in deck.shapes(rc) if s.media)
        room_ext = os.path.splitext(room_shape_clean.media)[1].lower()
        room_out = os.path.join(out_room, f"{art_id}{room_ext}")
        with open(room_out, "wb") as fh:
            fh.write(deck.media_bytes(room_shape_clean.media))
        room_w, room_h = image_size(room_out)

        # ----- floorplan correct location = red dot center -----------------
        floor_rect = next(s.rect for s in fshapes if deck.media_hash(s.media) == floor_hash)
        dot = next(s for s in fshapes if deck.media_hash(s.media) == dot_hash)
        fnx, fny = norm_within(floor_rect, dot.cx, dot.cy)
        fpx, fpy = fnx * floor_w, fny * floor_h

        # ----- room correct location = centroid of red bounding box --------
        kshapes = deck.shapes(rk)
        room_rect = next(s.rect for s in kshapes if deck.media_hash(s.media) is not None)
        red_lines = [s for s in kshapes if s.prst == "line" and RED_HEX in s.fills]
        if len(red_lines) < 4:
            # Fall back to any red-filled shapes (rect etc.).
            red_lines = [s for s in kshapes if RED_HEX in s.fills and s.media is None]
        xs = [v for s in red_lines for v in (s.rect[0], s.rect[2])]
        ys = [v for s in red_lines for v in (s.rect[1], s.rect[3])]
        box = (min(xs), min(ys), max(xs), max(ys))
        bcx, bcy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        rnx, rny = norm_within(room_rect, bcx, bcy)
        rpx, rpy = rnx * room_w, rny * room_h
        # Normalized box extents (handy for tolerance-based scoring later).
        bx0, by0 = norm_within(room_rect, box[0], box[1])
        bx1, by1 = norm_within(room_rect, box[2], box[3])

        flagged = not (0 <= fnx <= 1 and 0 <= fny <= 1 and 0 <= rnx <= 1 and 0 <= rny <= 1)

        coord_rows.append(dict(
            artwork_id=art_id,
            artwork_file=os.path.basename(art_out),
            room_file=os.path.basename(room_out),
            artwork_img_w=art_w, artwork_img_h=art_h,
            floor_img_w=floor_w, floor_img_h=floor_h,
            floor_correct_px_x=round(fpx, 2), floor_correct_px_y=round(fpy, 2),
            floor_correct_norm_x=round(fnx, 6), floor_correct_norm_y=round(fny, 6),
            room_img_w=room_w, room_img_h=room_h,
            room_correct_px_x=round(rpx, 2), room_correct_px_y=round(rpy, 2),
            room_correct_norm_x=round(rnx, 6), room_correct_norm_y=round(rny, 6),
            room_box_norm_x0=round(min(bx0, bx1), 6), room_box_norm_y0=round(min(by0, by1), 6),
            room_box_norm_x1=round(max(bx0, bx1), 6), room_box_norm_y1=round(max(by0, by1), 6),
            flagged=int(flagged),
        ))
        floor_diag.append((art_id, floor_out, fnx, fny, flagged))
        room_diag.append((art_id, room_out, rnx, rny, min(bx0, bx1), min(by0, by1),
                          max(bx0, bx1), max(by0, by1), flagged))

    # --- Write coordinates.csv --------------------------------------------
    coord_path = os.path.join(out_data, "coordinates.csv")
    with open(coord_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(coord_rows[0].keys()))
        w.writeheader()
        w.writerows(coord_rows)

    # --- Write metadata template (artwork_type left blank to fill in). -----
    meta_path = os.path.join(out_data, "metadata_template.csv")
    with open(meta_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["artwork_id", "artwork_type", "artist", "title", "room"])
        for r in coord_rows:
            w.writerow([r["artwork_id"], "", "", "", ""])

    # --- Diagnostics: self-contained HTML with the marker drawn over each
    #     image (base64-embedded, no external deps, opens in any browser). ---
    _write_floor_diag(os.path.join(out_diag, "floorplan_overlays.html"), floor_diag)
    _write_room_diag(os.path.join(out_diag, "room_overlays.html"), room_diag)

    flagged_n = sum(r["flagged"] for r in coord_rows)
    print(f"[extract] floorplan image: {os.path.basename(floor_out)} ({floor_w}x{floor_h})")
    print(f"[extract] wrote {len(coord_rows)} trials -> {coord_path}")
    print(f"[extract] metadata template -> {meta_path}")
    print(f"[extract] diagnostics -> {out_diag}/")
    print(f"[extract] flagged (out-of-bounds) trials: {flagged_n}")
    if flagged_n:
        print("          Review diagnostics before proceeding.")


# --------------------------------------------------------------------------
# Diagnostics writers (pure HTML/CSS, base64-embedded images)
# --------------------------------------------------------------------------

def _b64(path: str) -> str:
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    with open(path, "rb") as fh:
        return f"data:image/{mime};base64," + base64.b64encode(fh.read()).decode()


def _write_floor_diag(out_html, rows):
    cells = []
    for art_id, img, nx, ny, flagged in rows:
        border = "#d00" if flagged else "#2a2"
        cells.append(f"""
        <figure style="margin:0">
          <div style="position:relative;border:3px solid {border}">
            <img src="{_b64(img)}" style="width:100%;display:block">
            <div style="position:absolute;left:{nx*100:.3f}%;top:{ny*100:.3f}%;
                 width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;
                 background:rgba(255,0,0,.85);box-shadow:0 0 0 2px #fff"></div>
          </div>
          <figcaption>{art_id} — floorplan ({nx:.3f}, {ny:.3f})</figcaption>
        </figure>""")
    _diag_page(out_html, "Floorplan answer-key QC", cells)


def _write_room_diag(out_html, rows):
    cells = []
    for art_id, img, nx, ny, x0, y0, x1, y1, flagged in rows:
        border = "#d00" if flagged else "#2a2"
        cells.append(f"""
        <figure style="margin:0">
          <div style="position:relative;border:3px solid {border}">
            <img src="{_b64(img)}" style="width:100%;display:block">
            <div style="position:absolute;left:{x0*100:.3f}%;top:{y0*100:.3f}%;
                 width:{(x1-x0)*100:.3f}%;height:{(y1-y0)*100:.3f}%;
                 border:2px solid rgba(255,0,0,.9)"></div>
            <div style="position:absolute;left:{nx*100:.3f}%;top:{ny*100:.3f}%;
                 width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%;
                 background:rgba(255,0,0,.9);box-shadow:0 0 0 2px #fff"></div>
          </div>
          <figcaption>{art_id} — room ({nx:.3f}, {ny:.3f})</figcaption>
        </figure>""")
    _diag_page(out_html, "Room answer-key QC", cells)


def _diag_page(out_html, title, cells):
    html = f"""<!doctype html><meta charset="utf-8"><title>{title}</title>
<style>
 body{{font:14px system-ui;margin:24px;background:#111;color:#eee}}
 h1{{font-size:18px}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
 figcaption{{padding:6px 2px;color:#bbb}}
</style>
<h1>{title}</h1>
<p>Red marker = detected correct location. Green border = OK, red border = flagged (out of bounds).</p>
<div class="grid">{''.join(cells)}</div>"""
    with open(out_html, "w") as fh:
        fh.write(html)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Extract CAPTURE stimuli & answer keys from the PPTX.")
    ap.add_argument("--pptx", default=DEFAULT_PPTX, help="Path to the stimulus PowerPoint deck.")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Project root (contains stimuli/, data/).")
    args = ap.parse_args(argv)
    if not os.path.isfile(args.pptx):
        sys.exit(f"ERROR: PPTX not found: {args.pptx}")
    extract(args.pptx, args.out)


if __name__ == "__main__":
    main()
