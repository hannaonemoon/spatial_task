# -*- coding: utf-8 -*-
"""
experiment.py
====================================================================
Session orchestration: startup dialog, validation, window setup,
instructions, the trial loop, crash recovery, and clean shutdown.

This is the top-level flow. It contains NO stimulus-specific numbers
(those live in config.py) and NO hardware code (that lives in
triggers.py). Run it via ../run_experiment.py.
====================================================================
"""

from __future__ import annotations

import sys

from psychopy import visual, core, event, gui, monitors, logging

from . import config, stimuli, data_io, triggers, trial


# --------------------------------------------------------------------------
# Instruction text (shown ONCE at the start)
# --------------------------------------------------------------------------
INSTRUCTIONS = (
    "Memory for Artwork Locations\n\n"
    "You will see one artwork at a time. For each artwork you will make TWO "
    "location judgments.\n\n"
    "1) FLOORPLAN: On the museum floorplan, click where you think the artwork "
    "was located.\n"
    "2) ROOM: You will then see a photo of the room (with the artwork removed). "
    "Click where you think the artwork was located in that room.\n\n"
    "   • For PAINTINGS and other wall-mounted works, click the CENTER of "
    "where the artwork was.\n"
    "   • For SCULPTURES, click the CENTER of the sculpture's FOOTPRINT "
    "(where it stood on the floor or pedestal).\n\n"
    "After each click you will rate your confidence: Low, Med, or High.\n\n"
    "Please respond as ACCURATELY as possible. You may respond quickly, but "
    "accuracy matters more than speed. There is no time limit.\n\n"
    "Click the mouse to begin."
)


# --------------------------------------------------------------------------
# Dialogs
# --------------------------------------------------------------------------

def _error_dialog(message: str, title: str = "Error") -> None:
    """Show a blocking error message using a plain Dlg (version-robust)."""
    dlg = gui.Dlg(title=title)
    for line in message.split("\n"):
        dlg.addText(line)
    dlg.show()


def startup_dialog() -> dict | None:
    """Collect participant info. Returns the info dict, or None if cancelled."""
    info = {
        "Participant ID": "",
        "Session": "1",
        "Researcher initials": "",
        "EEG Trigger Mode": config.TRIGGER_MODES,   # list -> dropdown
        "Debug mode (few trials, windowed)": False,
    }
    order = ["Participant ID", "Session", "Researcher initials",
             "EEG Trigger Mode", "Debug mode (few trials, windowed)"]
    dlg = gui.DlgFromDict(dictionary=info, title=config.EXPERIMENT_NAME, order=order)
    if not dlg.OK:
        return None
    if not str(info["Participant ID"]).strip():
        _error_dialog("Participant ID is required.")
        return startup_dialog()
    return info


def ask_resume(n_done, n_total) -> bool:
    dlg = gui.Dlg(title="Resume session?")
    dlg.addText(f"An interrupted session was found: {n_done}/{n_total} trials done.")
    dlg.addField("Action:", choices=["Resume", "Start over (new file)"])
    out = dlg.show()
    return dlg.OK and out[0] == "Resume"


# --------------------------------------------------------------------------
# Window
# --------------------------------------------------------------------------

def make_window(debug: bool) -> visual.Window:
    mon = monitors.Monitor(config.MONITOR_NAME)
    # Set sensible values if this monitor isn't calibrated on the machine.
    if mon.getWidth() is None:
        mon.setWidth(config.MONITOR_WIDTH_CM)
    if mon.getDistance() is None:
        mon.setDistance(config.MONITOR_DISTANCE_CM)
    if not mon.getSizePix():
        mon.setSizePix(list(config.MONITOR_RESOLUTION))

    fullscr = (not debug) and config.FULLSCREEN
    size = config.DEBUG_WINDOW_SIZE if debug else config.MONITOR_RESOLUTION
    # 'height' units make the layout resolution- and Retina-independent.
    win = visual.Window(size=size, fullscr=fullscr, monitor=mon, units="height",
                        color=config.BACKGROUND_COLOR, colorSpace="rgb",
                        allowGUI=False, waitBlanking=True)
    win.mouseVisible = True
    return win


def show_message(win, text, wait_click=True):
    """Show a full-screen message; advance on mouse click (or any key)."""
    aspect = float(win.size[0]) / float(win.size[1])
    msg = visual.TextStim(win, text=text, units="height", color=config.TEXT_COLOR,
                          height=0.030, wrapWidth=0.80 * aspect, alignText="left")
    mouse = event.Mouse(win=win)
    mouse.clickReset()
    event.clearEvents()
    prev = mouse.getPressed()[0]
    while True:
        if event.getKeys(keyList=config.QUIT_KEYS):
            raise KeyboardInterrupt("Quit key pressed.")
        if event.getKeys():           # any key advances
            return
        msg.draw()
        win.flip()
        pressed = mouse.getPressed()[0]
        if pressed and not prev:
            return
        prev = pressed
        if not wait_click:
            return


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def run():
    # 1) Validate stimuli/coordinates BEFORE doing anything user-facing.
    try:
        specs = stimuli.load_specs(strict=True)
        floorplan_path = stimuli.floorplan_path()
        floor_labels = stimuli.load_floorplan_labels()
    except stimuli.StimulusError as exc:
        _error_dialog(str(exc), title="Stimulus validation failed")
        print("[FATAL]", exc)
        return
    spec_by_id = {s.artwork_id: s for s in specs}
    all_ids = [s.artwork_id for s in specs]

    # 2) Startup dialog.
    info = startup_dialog()
    if info is None:
        print("Cancelled at startup dialog.")
        return

    participant = str(info["Participant ID"]).strip()
    session_id = str(info["Session"]).strip()
    researcher = str(info["Researcher initials"]).strip()
    trigger_mode = info["EEG Trigger Mode"]
    debug = bool(info["Debug mode (few trials, windowed)"])

    # 3) Recovery check.
    completed_ids: set = set()
    resumable = data_io.find_resumable(participant, session_id)
    if resumable is not None:
        sess, done = resumable
        if ask_resume(len(done), len(sess.order)):
            session = sess
            completed_ids = done
        else:
            session = data_io.Session.create(
                participant, session_id, researcher, trigger_mode, debug,
                config.MONITOR_RESOLUTION, all_ids)
    else:
        session = data_io.Session.create(
            participant, session_id, researcher, trigger_mode, debug,
            config.MONITOR_RESOLUTION, all_ids)

    # 4) Window + record actual resolution.
    win = make_window(debug)
    session.monitor_resolution = [int(win.size[0]), int(win.size[1])]
    recorder = data_io.DataRecorder(session)

    # 5) Trigger + logging.
    logging.console.setLevel(logging.WARNING)
    trigger = triggers.make_trigger(trigger_mode, logger=lambda m: logging.warning(m))
    mouse = event.Mouse(win=win)

    # 6) Instructions (once) — skip if resuming mid-session.
    aborted = False
    try:
        if not completed_ids:
            show_message(win, INSTRUCTIONS)

        # 7) Trial loop over the (persisted) randomized order.
        for position, art_id in enumerate(session.order, start=1):
            if art_id in completed_ids:
                continue
            trial_number = position
            row = trial.run_trial(
                win, mouse, spec_by_id[art_id], trigger,
                floorplan_path, floor_labels,
                trial_number=trial_number, order_position=trial_number)
            # provenance that's constant per session
            row.update(participant=participant, session=session_id,
                       researcher=researcher, trigger_mode=trigger_mode,
                       random_seed=session.seed, debug=int(debug),
                       randomized_order="|".join(session.order),
                       monitor_resolution=f"{win.size[0]}x{win.size[1]}")
            recorder.write_trial(row)

        trigger.send("block_end")
        show_message(win, "You have completed the task.\n\nThank you!\n\n"
                          "Please wait for the researcher.")
    except KeyboardInterrupt:
        aborted = True
        print("[experiment] Aborted by experimenter; completed trials are saved.")
    finally:
        trigger.close()
        win.close()

    print(f"[experiment] Data: {recorder.csv_path}")
    if aborted:
        print("[experiment] Session INCOMPLETE — re-run with the same "
              "Participant ID + Session to resume.")
    core.quit()
