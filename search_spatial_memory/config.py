# -*- coding: utf-8 -*-
"""
config.py
====================================================================
Central configuration for the CAPTURE spatial-memory experiment.

Everything a future experimenter is likely to tweak lives here:
paths, timing, geometry, colors, and run modes. No trial logic in
this file -- it is data only, so it can be read and edited safely
without understanding the rest of the codebase.

All paths are RELATIVE to the project root (the folder that contains
`stimuli/`, `data/`, and this `search_spatial_memory/` package), so
the whole project can be copied or moved without edits.
====================================================================
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------
# Version + identity
# --------------------------------------------------------------------------
EXPERIMENT_NAME = "CAPTURE_spatial_memory"
EXPERIMENT_VERSION = "1.0.0"          # bump on any change to trial logic/data schema

# --------------------------------------------------------------------------
# Project paths (resolved relative to this file -> project root)
# --------------------------------------------------------------------------
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)

STIM_DIR = os.path.join(PROJECT_ROOT, "stimuli")
ARTWORK_DIR = os.path.join(STIM_DIR, "artworks")
ROOM_DIR = os.path.join(STIM_DIR, "room_clean")
FLOORPLAN_DIR = os.path.join(STIM_DIR, "floorplan")

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
COORDINATES_CSV = os.path.join(DATA_DIR, "coordinates.csv")
METADATA_CSV = os.path.join(DATA_DIR, "metadata.csv")
# Optional map from ART0xx -> the artwork's real name (used across the
# recognition-memory test). If present, the name is logged in each trial row.
CODEKEY_CSV = os.path.join(DATA_DIR, "codekey.csv")
FLOORPLAN_LABELS_CSV = os.path.join(FLOORPLAN_DIR, "floorplan_labels.csv")

# Where per-participant output is written.
RESULTS_DIR = os.path.join(DATA_DIR, "results")

N_TRIALS = 48

# --------------------------------------------------------------------------
# Run modes
# --------------------------------------------------------------------------
# DEBUG_MODE is chosen at runtime from the startup dialog; these are the
# defaults / parameters the two modes use.
DEBUG_N_TRIALS = 4                     # trials to run in debug mode
DEBUG_WINDOW_SIZE = (1280, 800)        # windowed size for debug
FULLSCREEN = True                      # production default (overridden in debug)

# EXPERIMENTER QA ONLY. When True, after each click the screen shows the
# CORRECT location (green marker) and the computed error, then waits for a key.
# This lets you *see* the real-time scoring without running all 48 trials.
# It MUST be False when testing real participants (it reveals the answer).
# Automatically ignored unless Debug mode is selected in the startup dialog.
SHOW_SCORE_FEEDBACK = False
CORRECT_MARKER_COLOR = "lime"          # color of the correct-location QA marker

# --------------------------------------------------------------------------
# Display
# --------------------------------------------------------------------------
# We work in PIXEL units throughout so mouse clicks map exactly to image
# coordinates. Define your lab monitor here for correct sizing / logging.
MONITOR_NAME = "capture_lab"
MONITOR_WIDTH_CM = 52.0                # physical width of the display
MONITOR_DISTANCE_CM = 60.0             # viewing distance
MONITOR_RESOLUTION = (1920, 1080)      # fallback if PsychoPy can't detect it

BACKGROUND_COLOR = (0.0, 0.0, 0.0)     # PsychoPy rgb [-1,1]; 0 = mid-grey
TEXT_COLOR = "white"

# Layout: the cue artwork sits on the LEFT, the map/room on the RIGHT.
# Boxes are given as fractions of the WINDOW, where cx/cy are measured from the
# center and ±0.5 == the screen edge (cx = fraction of width, cy = fraction of
# height); w/h are fractions of width/height. ui.py converts these to
# resolution-independent 'height' units at runtime, so the layout looks the
# same on any monitor (including Retina). Images preserve aspect ratio and are
# scaled to fit inside their box. Keep |cx| + w/2 <= 0.5 to stay on-screen.
ARTWORK_BOX = dict(cx=-0.32, cy=0.08, w=0.26, h=0.54)   # left: artwork cue (smaller)
SCENE_BOX = dict(cx=0.20, cy=0.09, w=0.58, h=0.80)      # right: floorplan / room (larger)

# Confidence widget geometry (bottom strip; must not overlap the scene box).
CONF_Y = -0.42                         # vertical center as fraction of height
CONF_BUTTON_W = 0.12                   # button width (frac of window width)
CONF_BUTTON_H = 0.08                   # button height (frac of window height)
CONF_BUTTON_GAP = 0.03                 # gap between buttons (frac of width)
CONF_LABELS = ["Low", "Med", "High"]

# Red click marker ("X"). Size is in 'height' units; line width is in pixels.
MARKER_COLOR = "red"
MARKER_SIZE_H = 0.014                  # half-length of each stroke of the X
MARKER_LINE_WIDTH = 4

# Floorplan orientation labels (START/END/projection). Re-drawn from the CSV
# produced by extract_from_pptx.py so subjects get the same cues they saw in
# the museum, without baking a red dot into the image.
SHOW_FLOORPLAN_LABELS = True
FLOORPLAN_LABEL_HEIGHT = 0.022         # text height as fraction of window height

# --------------------------------------------------------------------------
# Timing (seconds)
# --------------------------------------------------------------------------
FIXATION_DURATION = 0.5                # inter-stage / inter-trial fixation
# There is NO response deadline for clicks or confidence (accuracy > speed).

# --------------------------------------------------------------------------
# EEG trigger modes (see triggers.py). The dialog offers these labels.
# --------------------------------------------------------------------------
TRIGGER_MODES = ["No EEG triggers", "Wearable Sensing Wireless Trigger Hub"]

# Canonical event labels sent via trigger.send(...). Keeping them here means
# the trial code references names, and the hardware mapping lives in one place.
TRIGGER_EVENTS = {
    "trial_onset": 10,
    "floorplan_onset": 11,
    "floorplan_click": 12,
    "floorplan_conf_onset": 13,
    "floorplan_conf_response": 14,
    "room_onset": 21,
    "room_click": 22,
    "room_conf_onset": 23,
    "room_conf_response": 24,
    "fixation_onset": 30,
    "block_end": 99,
}

# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------
QUIT_KEYS = ["escape"]                 # abort the experiment (data already saved per-trial)
