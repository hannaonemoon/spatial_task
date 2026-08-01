# -*- coding: utf-8 -*-
"""
trial.py
====================================================================
The two-stage memory trial.

For one artwork:
  Stage 1 (Floorplan memory)
    - artwork (left) + floorplan (right) appear together, no deadline;
    - first valid click INSIDE the floorplan is accepted immediately;
    - a red X is drawn and stays; error is computed silently;
    - Low/Med/High confidence is collected (mouse), no deadline;
    - 500 ms fixation.
  Stage 2 (Room placement)
    - floorplan is replaced by the art-removed room photo (artwork stays);
    - first valid click INSIDE the room is accepted immediately;
    - red X stays; error computed silently;
    - confidence; 500 ms fixation.

Returns a flat dict (one row) for data_io. No accuracy feedback is ever
shown. Timing-critical onsets are marked with trigger.send(...).
====================================================================
"""

from __future__ import annotations

from datetime import datetime

from psychopy import core

from . import config, ui, scoring


def _fixation(win, fixation_stim, trigger):
    trigger.send("fixation_onset")
    fixation_stim.draw()
    win.flip()
    core.wait(config.FIXATION_DURATION)


def run_trial(win, mouse, spec, trigger, floorplan_path, floor_labels,
              trial_number, order_position):
    """
    Run one complete two-stage trial.

    Parameters
    ----------
    win, mouse       : PsychoPy Window and Mouse.
    spec             : stimuli.ArtworkSpec for this trial.
    trigger          : a triggers.BaseTrigger.
    floorplan_path   : path to the shared floorplan image.
    floor_labels     : list of label dicts (may be empty).
    trial_number     : 1-based index in the presentation sequence.
    order_position   : same as trial_number (kept explicit for clarity/logging).

    Returns
    -------
    dict : one flat data row.
    """
    # ---- Build stimuli (preloaded per trial) -----------------------------
    art_px = spec.artwork_img_px if all(spec.artwork_img_px) else None
    artwork = ui.place_image(win, spec.artwork_path, config.ARTWORK_BOX, src_px=art_px)
    floorplan = ui.place_image(win, floorplan_path, config.SCENE_BOX, spec.floor_img_px)
    room = ui.place_image(win, spec.room_path, config.SCENE_BOX, spec.room_img_px)
    fixation = ui.make_fixation(win)
    conf_widget = ui.ConfidenceWidget(win)
    label_stims = ui.make_floorplan_labels(win, floorplan, floor_labels) \
        if config.SHOW_FLOORPLAN_LABELS else []

    trigger.send("trial_onset")

    # =====================================================================
    # STAGE 1 — Floorplan memory
    # =====================================================================
    trigger.send("floorplan_onset")
    scene = [artwork, floorplan] + label_stims
    click_pos, floor_rt = ui.wait_for_click_in(win, mouse, floorplan, extra_draw=scene)
    trigger.send("floorplan_click")

    floor_marker = ui.make_marker(win, click_pos)
    floor_click_norm = floorplan.screen_to_norm(click_pos)
    floor_err = scoring.score(floor_click_norm, spec.floor_correct_norm, spec.floor_img_px)

    # Experimenter QA: optionally reveal correct location + error (never for subjects)
    if config.SHOW_SCORE_FEEDBACK:
        ui.show_score_qa(win, scene + [floor_marker],
                         floorplan.norm_to_screen(spec.floor_correct_norm),
                         floor_err, "floorplan")

    # Confidence (artwork + floorplan + red X remain visible)
    trigger.send("floorplan_conf_onset")
    scene_with_marker = scene + [floor_marker]
    floor_conf, floor_conf_rt = ui.wait_for_confidence(
        win, mouse, conf_widget, extra_draw=scene_with_marker)
    trigger.send("floorplan_conf_response")

    _fixation(win, fixation, trigger)

    # =====================================================================
    # STAGE 2 — Room placement
    # =====================================================================
    trigger.send("room_onset")
    scene2 = [artwork, room]
    click_pos2, room_rt = ui.wait_for_click_in(win, mouse, room, extra_draw=scene2)
    trigger.send("room_click")

    room_marker = ui.make_marker(win, click_pos2)
    room_click_norm = room.screen_to_norm(click_pos2)
    room_err = scoring.score(room_click_norm, spec.room_correct_norm, spec.room_img_px)

    if config.SHOW_SCORE_FEEDBACK:
        ui.show_score_qa(win, scene2 + [room_marker],
                         room.norm_to_screen(spec.room_correct_norm),
                         room_err, "room")

    trigger.send("room_conf_onset")
    scene2_with_marker = scene2 + [room_marker]
    room_conf, room_conf_rt = ui.wait_for_confidence(
        win, mouse, conf_widget, extra_draw=scene2_with_marker)
    trigger.send("room_conf_response")

    _fixation(win, fixation, trigger)

    # ---- Assemble the data row ------------------------------------------
    row = dict(
        # identity / provenance
        experiment=config.EXPERIMENT_NAME,
        experiment_version=config.EXPERIMENT_VERSION,
        datetime=datetime.now().isoformat(timespec="seconds"),
        # trial indexing
        trial_number=trial_number,
        order_position=order_position,
        artwork_id=spec.artwork_id,
        artwork_name=spec.artwork_name,
        artwork_type=spec.artwork_type,
        room_id=spec.room,
        artist=spec.artist,
        title=spec.title,
        artwork_file=spec.artwork_path.split("/")[-1],
        room_file=spec.room_path.split("/")[-1],
        floorplan_file=floorplan_path.split("/")[-1],
        # displayed image sizes (screen px) — useful for reconstructing geometry
        artwork_disp_w=round(artwork.disp_w, 1), artwork_disp_h=round(artwork.disp_h, 1),
        floor_disp_w=round(floorplan.disp_w, 1), floor_disp_h=round(floorplan.disp_h, 1),
        room_disp_w=round(room.disp_w, 1), room_disp_h=round(room.disp_h, 1),
        # click positions in raw SCREEN pixels (center-origin, +y up)
        floor_click_screen_x=round(click_pos[0], 1), floor_click_screen_y=round(click_pos[1], 1),
        room_click_screen_x=round(click_pos2[0], 1), room_click_screen_y=round(click_pos2[1], 1),
        # responses / RTs
        floor_rt=round(floor_rt, 4),
        floor_confidence=floor_conf,
        floor_confidence_rt=round(floor_conf_rt, 4),
        room_rt=round(room_rt, 4),
        room_confidence=room_conf,
        room_confidence_rt=round(room_conf_rt, 4),
    )
    # error measures (click/correct norm+px, signed errors, %diagonal)
    row.update(floor_err.as_row("floor_"))
    row.update(room_err.as_row("room_"))
    return row
