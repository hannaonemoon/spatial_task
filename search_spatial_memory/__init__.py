# -*- coding: utf-8 -*-
"""
search_spatial_memory
====================================================================
PsychoPy implementation of the CAPTURE spatial-memory task: memory
for the locations of 48 museum artworks, tested via a floorplan
localization stage and an in-room localization stage.

Modules
-------
config     : all tunable parameters, paths, timing, geometry.
triggers   : modular EEG trigger interface (Null + Wearable Sensing).
scoring    : spatial error metrics (pure math).
stimuli    : load + validate coordinates/metadata; resolve stimulus files.
data_io    : per-trial CSV, seed/order persistence, crash recovery.
ui         : image placement, click<->image mapping, marker, confidence.
trial      : the two-stage trial.
experiment : session flow (dialog, instructions, loop, shutdown).

Entry point: ../run_experiment.py
"""

__version__ = "1.0.0"
