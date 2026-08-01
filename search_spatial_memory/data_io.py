# -*- coding: utf-8 -*-
"""
data_io.py
====================================================================
Data recording, randomization persistence, and crash recovery.

Design goals (from the spec):
  * Save data after EVERY completed trial (append-on-write), so an
    interruption never loses more than the trial in progress.
  * Persist the random seed and the complete randomized order so a
    session can be reproduced exactly, or RESUMED after a crash.
  * Keep one flat, analysis-ready CSV per participant/session.

Files written under data/results/:
  sub-<PID>_ses-<SES>_<timestamp>.csv     -- one row per completed trial
  sub-<PID>_ses-<SES>_<timestamp>.json    -- session state (seed, order,
                                             completed trials, metadata)
====================================================================
"""

from __future__ import annotations

import csv
import glob
import json
import os
import random
from datetime import datetime

from . import config


def _slug(s: str) -> str:
    return "".join(c for c in str(s) if c.isalnum() or c in "-_") or "NA"


class Session:
    """Holds identity + randomization for one run, and (de)serializes it."""

    def __init__(self, participant, session, researcher, trigger_mode,
                 debug, monitor_resolution, order, seed, timestamp=None):
        self.participant = participant
        self.session = session
        self.researcher = researcher
        self.trigger_mode = trigger_mode
        self.debug = debug
        self.monitor_resolution = list(monitor_resolution)
        self.order = list(order)              # list of artwork_ids, in run order
        self.seed = seed
        self.timestamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.version = config.EXPERIMENT_VERSION

    # ---- factory ---------------------------------------------------------
    @classmethod
    def create(cls, participant, session, researcher, trigger_mode, debug,
               monitor_resolution, artwork_ids, seed=None):
        """
        Build a new session, randomizing trial order with a reproducible seed.
        If `seed` is None one is drawn and stored so the order can be recreated.
        """
        if seed is None:
            seed = random.SystemRandom().randrange(1, 2 ** 31 - 1)
        rng = random.Random(seed)
        order = list(artwork_ids)
        rng.shuffle(order)
        if debug:
            order = order[:config.DEBUG_N_TRIALS]
        return cls(participant, session, researcher, trigger_mode, debug,
                   monitor_resolution, order, seed)

    # ---- serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        return dict(participant=self.participant, session=self.session,
                    researcher=self.researcher, trigger_mode=self.trigger_mode,
                    debug=self.debug, monitor_resolution=self.monitor_resolution,
                    order=self.order, seed=self.seed, timestamp=self.timestamp,
                    version=self.version)

    @classmethod
    def from_dict(cls, d) -> "Session":
        s = cls(d["participant"], d["session"], d["researcher"], d["trigger_mode"],
                d["debug"], d["monitor_resolution"], d["order"], d["seed"],
                d.get("timestamp"))
        s.version = d.get("version", config.EXPERIMENT_VERSION)
        return s

    # ---- file naming -----------------------------------------------------
    @property
    def basename(self) -> str:
        return f"sub-{_slug(self.participant)}_ses-{_slug(self.session)}_{self.timestamp}"


# --------------------------------------------------------------------------
# Recovery: find an interrupted session for the same participant/session
# --------------------------------------------------------------------------

def find_resumable(participant, session) -> tuple[Session, set] | None:
    """
    Look for an existing session JSON for this participant+session whose CSV
    has fewer rows than its planned order (i.e. it was interrupted).

    Returns (Session, completed_artwork_ids) for the most recent match, or
    None if there is nothing to resume.
    """
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    pattern = os.path.join(config.RESULTS_DIR,
                           f"sub-{_slug(participant)}_ses-{_slug(session)}_*.json")
    candidates = sorted(glob.glob(pattern), reverse=True)
    for jpath in candidates:
        try:
            with open(jpath) as fh:
                sess = Session.from_dict(json.load(fh))
        except Exception:
            continue
        cpath = jpath[:-5] + ".csv"
        completed = set()
        if os.path.isfile(cpath):
            with open(cpath, newline="") as fh:
                for row in csv.DictReader(fh):
                    completed.add(row.get("artwork_id"))
        if len(completed) < len(sess.order):
            return sess, completed
    return None


# --------------------------------------------------------------------------
# Recorder: writes the session JSON and appends trial rows
# --------------------------------------------------------------------------

class DataRecorder:
    """Owns the output files for one Session and appends trial rows safely."""

    def __init__(self, session: Session):
        os.makedirs(config.RESULTS_DIR, exist_ok=True)
        self.session = session
        base = os.path.join(config.RESULTS_DIR, session.basename)
        self.csv_path = base + ".csv"
        self.json_path = base + ".json"
        self._fieldnames = None
        self._save_session_state()

    def _save_session_state(self):
        with open(self.json_path, "w") as fh:
            json.dump(self.session.to_dict(), fh, indent=2)

    def write_trial(self, row: dict):
        """
        Append one trial row. On the first write the header is created from the
        row's keys; subsequent rows are aligned to that header. Flushed + fsync'd
        so an interruption cannot lose a completed trial.
        """
        new_file = not os.path.isfile(self.csv_path)
        if self._fieldnames is None:
            if new_file:
                self._fieldnames = list(row.keys())
            else:
                with open(self.csv_path, newline="") as fh:
                    self._fieldnames = next(csv.reader(fh))
        with open(self.csv_path, "a", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=self._fieldnames,
                                    extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(row)
            fh.flush()
            os.fsync(fh.fileno())
