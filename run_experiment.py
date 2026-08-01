#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_experiment.py
====================================================================
Entry point for the CAPTURE spatial-memory experiment.

Usage
-----
From this project folder, using your PsychoPy Python:

    python run_experiment.py

or launch it from the PsychoPy Coder ("Run") -- open THIS file.

A startup dialog collects Participant ID, Session, Researcher initials,
the EEG trigger mode, and a Debug checkbox (a few trials in a windowed
display). Everything else (stimulus validation, randomization, data
saving, crash recovery) is handled by the `search_spatial_memory`
package.

Prerequisites
-------------
1. PsychoPy installed (Standalone app, or `pip install psychopy`).
2. Preprocessing already run so that data/coordinates.csv and the
   stimuli/ folders exist:
       python preprocessing/extract_from_pptx.py --pptx "<deck>.pptx"
   (Validate any time with: python preprocessing/validate_stimuli.py)
====================================================================
"""

import os
import sys

# Ensure the package is importable no matter where Python is launched from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from search_spatial_memory import experiment

if __name__ == "__main__":
    experiment.run()
