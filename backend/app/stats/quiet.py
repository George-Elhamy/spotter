"""Quiet-window estimates for event types and restart signals."""
from __future__ import annotations

import math

_DURATIONS = {
    "throw_in": 6.0,
    "goal_kick": 8.0,
    "free_kick": 12.0,
    "corner": 15.0,
    "substitution": 25.0,
    "card": 20.0,
    "goal": 40.0,
    "injury": 40.0,
    "var_check": 60.0,
    "var_decision": 60.0,
    "half_time": math.inf,
}


def quiet_window(event: dict) -> float | None:
    kind = event.get("type")
    if kind in _DURATIONS:
        return _DURATIONS[kind]
    restart = event.get("restart")
    if restart in _DURATIONS:
        return _DURATIONS[restart]
    return None
