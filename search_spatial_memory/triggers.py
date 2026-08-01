# -*- coding: utf-8 -*-
"""
triggers.py
====================================================================
Modular EEG trigger interface.

The experiment never contains hardware-specific code. It simply calls:

    trigger.send("floorplan_onset")

The concrete class behind `trigger` decides what that means. For the
first version we ship:

  * NullTrigger              -- does nothing (No EEG triggers)
  * WearableSensingTrigger   -- placeholder for the Wearable Sensing
                                Wireless Trigger Hub; documented stubs
                                only, safe to run.

To add real hardware later, implement `_emit(code, label)` in a new
subclass (or fill in WearableSensingTrigger._emit) and register it in
`make_trigger()`. No other file needs to change.
====================================================================
"""

from __future__ import annotations

import time

from . import config


class BaseTrigger:
    """Abstract trigger. Maps event labels -> integer codes and timestamps."""

    def __init__(self, event_map=None, logger=None):
        self.event_map = event_map or config.TRIGGER_EVENTS
        self.logger = logger              # optional callable(msg) for logging
        self.log = []                     # list of (label, code, time) for the record

    # ---- public API ------------------------------------------------------
    def send(self, label: str) -> None:
        """Send the trigger for `label`. Unknown labels are logged, not fatal."""
        code = self.event_map.get(label)
        t = time.perf_counter()
        self.log.append((label, code, t))
        if code is None:
            self._warn(f"[trigger] unknown event label: {label!r} (no code sent)")
            return
        try:
            self._emit(code, label)
        except Exception as exc:                        # never let a trigger crash a session
            self._warn(f"[trigger] emit failed for {label!r}: {exc}")

    def close(self) -> None:
        """Release any hardware resources. Safe to call multiple times."""
        pass

    # ---- to override -----------------------------------------------------
    def _emit(self, code: int, label: str) -> None:
        raise NotImplementedError

    def _warn(self, msg: str) -> None:
        if self.logger:
            self.logger(msg)
        else:
            print(msg)


class NullTrigger(BaseTrigger):
    """No-op trigger used when EEG is not being recorded."""

    def _emit(self, code: int, label: str) -> None:
        # Intentionally does nothing. The event is still recorded in self.log.
        pass


class WearableSensingTrigger(BaseTrigger):
    """
    Placeholder for the Wearable Sensing Wireless Trigger Hub.

    The Trigger Hub typically accepts marker codes over a serial/USB or UDP
    connection (see your device's SDK). This class documents where that code
    goes but performs NO hardware I/O yet, so selecting this mode is safe and
    will not block a session.

    To enable real triggers:
      1. Open the device in __init__ (e.g. serial.Serial(port, baud) or a
         socket to the hub), storing the handle on self.
      2. Implement _emit() to write `code` to that handle.
      3. Release it in close().
    """

    def __init__(self, event_map=None, logger=None, port=None):
        super().__init__(event_map, logger)
        self.port = port
        self._device = None
        # --- Placeholder: real initialization would happen here. ----------
        # Example (pseudo-code, DO NOT UNCOMMENT until hardware is present):
        #   import serial
        #   self._device = serial.Serial(port or "COM3", baudrate=115200, timeout=0)
        self._warn("[trigger] WearableSensing selected: running in PLACEHOLDER "
                   "mode (no hardware I/O). See triggers.py to enable.")

    def _emit(self, code: int, label: str) -> None:
        # --- Placeholder: real emit would write the marker code. ----------
        # Example (pseudo-code):
        #   self._device.write(bytes([code]))
        # For now we do nothing but the event is recorded in self.log.
        pass

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None


def make_trigger(mode_label: str, logger=None) -> BaseTrigger:
    """
    Factory: return the trigger implementation for a dialog `mode_label`.

    Unknown labels fall back to NullTrigger so the experiment always runs.
    """
    if mode_label == "Wearable Sensing Wireless Trigger Hub":
        return WearableSensingTrigger(logger=logger)
    return NullTrigger(logger=logger)
