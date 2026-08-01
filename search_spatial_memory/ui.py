# -*- coding: utf-8 -*-
"""
ui.py
====================================================================
PsychoPy presentation helpers: image placement with exact click
mapping, the red "X" click marker, the confidence widget, and the
fixation cross.

Coordinate conventions
----------------------
* The window uses PsychoPy 'height' UNITS, which are resolution- and
  Retina-independent: 1 unit == the window HEIGHT. The visible area is
  y in [-0.5, +0.5] and x in [-aspect/2, +aspect/2], where
  aspect = window_width / window_height. Center = (0, 0), +y is UP.
  Using 'height' avoids all pixel/framebuffer scaling problems on
  HiDPI (Retina) displays.

* config layout boxes are given as fractions of the WINDOW: cx is a
  fraction of width in [-0.5, 0.5] (±0.5 = left/right edge), cy a
  fraction of height, w/h fractions of width/height. `_to_height()`
  converts those to height units using the live aspect ratio.

* Correct/click locations are stored as NORMALIZED image coordinates
  in [0, 1] with the origin at the TOP-LEFT of the image and +y DOWN
  (image/pixel convention). All conversions live in `DisplayImage`, so
  the rest of the code never juggles coordinate frames.

This module imports PsychoPy; import it only in the experiment runtime
(not from the dependency-light preprocessing scripts).
====================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

from psychopy import visual, event

from . import config


def _aspect(win) -> float:
    """Window aspect ratio (width/height). Ratio is correct even on Retina."""
    w, h = win.size
    return float(w) / float(h)


def _box_to_height(win, box):
    """
    Convert a config layout box (fractions of the window) into height units.

    Returns (cx, cy, w, h) in height units: x uses the aspect-scaled extent,
    y/heights use the [-0.5, 0.5] vertical extent.
    """
    a = _aspect(win)
    cx = box["cx"] * a
    cy = box["cy"]
    w = box["w"] * a
    h = box["h"]
    return cx, cy, w, h


# --------------------------------------------------------------------------
# Image placement + coordinate mapping
# --------------------------------------------------------------------------

@dataclass
class DisplayImage:
    """
    An ImageStim placed inside a layout box, plus the geometry needed to
    convert between screen (height-unit) positions and normalized image
    coordinates. All of cx/cy/disp_w/disp_h are in height units; the
    conversion math is unit-agnostic.
    """
    stim: visual.ImageStim
    cx: float
    cy: float
    disp_w: float
    disp_h: float
    src_px: tuple[int, int]           # source image size (w, h) in pixels

    @property
    def left(self) -> float:
        return self.cx - self.disp_w / 2.0

    @property
    def top(self) -> float:
        return self.cy + self.disp_h / 2.0        # top edge = largest y

    def contains(self, pos) -> bool:
        x, y = pos
        return (self.left <= x <= self.left + self.disp_w and
                self.cy - self.disp_h / 2.0 <= y <= self.top)

    def screen_to_norm(self, pos) -> tuple[float, float]:
        """Screen position -> normalized image coords (top-left origin)."""
        x, y = pos
        nx = (x - self.left) / self.disp_w
        ny = (self.top - y) / self.disp_h          # flip: +y down in image space
        return nx, ny

    def norm_to_screen(self, norm) -> tuple[float, float]:
        """Normalized image coords (top-left origin) -> screen position."""
        nx, ny = norm
        return self.left + nx * self.disp_w, self.top - ny * self.disp_h

    def draw(self):
        self.stim.draw()


def place_image(win, image_path, box, src_px=None) -> DisplayImage:
    """
    Create a DisplayImage fitting `image_path` inside `box`, preserving aspect
    ratio. Works entirely in height units.

    `src_px` is the source image's (width, height) in pixels; it sets the image
    aspect ratio and is retained for pixel-space error reporting. If None (e.g.
    the artwork cue, which isn't scored) the native size is detected.
    """
    box_cx, box_cy, box_w, box_h = _box_to_height(win, box)

    # Aspect ratio comes from the source pixel size. It is normally supplied
    # (from coordinates.csv); if not, read the file's native size via PIL,
    # which ships with PsychoPy.
    if src_px is None:
        from PIL import Image
        with Image.open(image_path) as im:
            src_px = im.size                      # (width, height) in pixels

    stim = visual.ImageStim(win, image=image_path, units="height",
                            pos=(box_cx, box_cy), interpolate=True)
    src_w, src_h = src_px
    img_aspect = src_w / src_h
    # Fit within the box while preserving aspect ratio.
    disp_h = min(box_h, box_w / img_aspect)
    disp_w = disp_h * img_aspect
    stim.size = (disp_w, disp_h)

    return DisplayImage(stim=stim, cx=box_cx, cy=box_cy,
                        disp_w=disp_w, disp_h=disp_h, src_px=src_px)


# --------------------------------------------------------------------------
# Red "X" click marker
# --------------------------------------------------------------------------

def make_marker(win, pos, color=None):
    """Return a drawable 'X' (two crossing lines) centered at `pos`."""
    s = config.MARKER_SIZE_H
    x, y = pos
    color = color or config.MARKER_COLOR
    line1 = visual.Line(win, start=(x - s, y - s), end=(x + s, y + s),
                        units="height", lineColor=color,
                        lineWidth=config.MARKER_LINE_WIDTH)
    line2 = visual.Line(win, start=(x - s, y + s), end=(x + s, y - s),
                        units="height", lineColor=color,
                        lineWidth=config.MARKER_LINE_WIDTH)
    return _Marker([line1, line2])


def show_score_qa(win, scene, correct_pos, err, stage_name):
    """
    EXPERIMENTER QA overlay (see config.SHOW_SCORE_FEEDBACK). Draws the scene
    plus a marker at the CORRECT location and a readout of the error metrics,
    then waits for a key press. Never shown to real participants.
    """
    correct = make_marker(win, correct_pos, color=config.CORRECT_MARKER_COLOR)
    txt = (f"[QA — {stage_name}]  green = correct location\n"
           f"Euclidean error: {err.err_norm_euclidean:.3f} (norm)   "
           f"{err.pct_of_diagonal:.1f}% of diagonal\n"
           f"H error: {err.err_norm_x:+.3f}   V error: {err.err_norm_y:+.3f}\n"
           f"press any key to continue")
    readout = visual.TextStim(win, text=txt, units="height", pos=(0, -0.40),
                              height=0.028, color="yellow", alignText="center")
    event.clearEvents()
    while True:
        for s in scene:
            s.draw()
        correct.draw()
        readout.draw()
        win.flip()
        if event.getKeys():
            return


class _Marker:
    """Tiny wrapper so a marker draws like any other stim."""
    def __init__(self, parts):
        self.parts = parts

    def draw(self):
        for p in self.parts:
            p.draw()


# --------------------------------------------------------------------------
# Confidence widget (Low / Med / High), mouse-selected, no time limit
# --------------------------------------------------------------------------

class ConfidenceWidget:
    """A row of clickable Low/Med/High buttons below the scene box."""

    def __init__(self, win):
        self.win = win
        a = _aspect(win)
        bw = config.CONF_BUTTON_W * a          # width fraction -> height units
        bh = config.CONF_BUTTON_H
        gap = config.CONF_BUTTON_GAP * a
        n = len(config.CONF_LABELS)
        total_w = n * bw + (n - 1) * gap
        x0 = -total_w / 2.0 + bw / 2.0
        y = config.CONF_Y

        self.title = visual.TextStim(win, text="Rate Your Confidence", units="height",
                                     pos=(0, y + bh), height=0.035,
                                     color=config.TEXT_COLOR)
        self.buttons = []
        for i, label in enumerate(config.CONF_LABELS):
            cx = x0 + i * (bw + gap)
            rect = visual.Rect(win, width=bw, height=bh, pos=(cx, y), units="height",
                               lineColor=config.TEXT_COLOR, fillColor=None, lineWidth=2)
            txt = visual.TextStim(win, text=label, pos=(cx, y), units="height",
                                  height=0.038, color=config.TEXT_COLOR)
            self.buttons.append((label, rect, txt, (cx, y, bw, bh)))

    def draw(self, highlight_label=None):
        self.title.draw()
        for label, rect, txt, _ in self.buttons:
            rect.fillColor = (0.2, 0.2, 0.2) if label == highlight_label else None
            rect.draw()
            txt.draw()

    def hit_test(self, pos) -> str | None:
        x, y = pos
        for label, rect, txt, (cx, cy, bw, bh) in self.buttons:
            if abs(x - cx) <= bw / 2.0 and abs(y - cy) <= bh / 2.0:
                return label
        return None


# --------------------------------------------------------------------------
# Fixation cross + floorplan labels
# --------------------------------------------------------------------------

def make_fixation(win):
    return visual.TextStim(win, text="+", units="height", height=0.06,
                           color=config.TEXT_COLOR, pos=(0, 0))


def make_floorplan_labels(win, display_image, labels):
    """
    Build START/END/projection TextStim overlays on the floorplan image,
    reproducing the deck's positions, rotation, and proportional font size so
    the map matches the intended landmark layout on any screen.
    """
    stims = []
    for lab in labels:
        pos = display_image.norm_to_screen((lab["norm_x"], lab["norm_y"]))
        hexval = lab["color_hex"]
        color = hexval if hexval.startswith("#") else "#" + hexval
        # Height scales with the displayed floorplan (height_frac is a fraction
        # of the floorplan image height); fall back to a fixed height if absent.
        hfrac = lab.get("height_frac", 0)
        height = hfrac * display_image.disp_h if hfrac else config.FLOORPLAN_LABEL_HEIGHT
        # PowerPoint `rot` and PsychoPy `ori` share the same on-screen sense
        # (positive = clockwise), so pass the rotation straight through.
        ori = lab.get("rotation_deg", 0)
        stims.append(visual.TextStim(win, text=lab["text"], units="height", pos=pos,
                                     height=height, color=color, bold=True,
                                     ori=ori, font="Arial"))
    return stims


# --------------------------------------------------------------------------
# Mouse helpers
# --------------------------------------------------------------------------

def wait_for_click_in(win, mouse, region, extra_draw=(), quit_keys=None):
    """
    Block until the FIRST left-click whose position is inside `region` (an
    object with .contains(pos)). Clicks outside are ignored. Returns
    (pos, rt_seconds). A quit key raises KeyboardInterrupt for a clean abort.
    """
    from psychopy import core
    quit_keys = quit_keys or config.QUIT_KEYS
    clock = core.Clock()
    mouse.clickReset()
    prev_pressed = mouse.getPressed()[0]

    while True:
        if event.getKeys(keyList=quit_keys):
            raise KeyboardInterrupt("Quit key pressed.")
        for s in extra_draw:
            s.draw()
        win.flip()

        pressed = mouse.getPressed()[0]
        if pressed and not prev_pressed:          # rising edge = fresh click
            pos = mouse.getPos()
            if region.contains(pos):
                return pos, clock.getTime()
        prev_pressed = pressed


def wait_for_confidence(win, mouse, widget, extra_draw=(), quit_keys=None):
    """
    Block until the participant clicks a confidence button. Returns
    (label, rt_seconds). Clicks elsewhere are ignored.
    """
    from psychopy import core
    quit_keys = quit_keys or config.QUIT_KEYS
    clock = core.Clock()
    mouse.clickReset()
    prev_pressed = mouse.getPressed()[0]

    while True:
        if event.getKeys(keyList=quit_keys):
            raise KeyboardInterrupt("Quit key pressed.")
        hover = widget.hit_test(mouse.getPos())
        for s in extra_draw:
            s.draw()
        widget.draw(highlight_label=hover)
        win.flip()

        pressed = mouse.getPressed()[0]
        if pressed and not prev_pressed:
            label = widget.hit_test(mouse.getPos())
            if label is not None:
                return label, clock.getTime()
        prev_pressed = pressed
