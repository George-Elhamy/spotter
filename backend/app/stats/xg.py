"""Small explainable expected-goals model for synthetic event data."""
from __future__ import annotations

import math


def expected_goals(event: dict, meta: dict | None = None) -> float:
    """Return event xG, honoring an explicit generator value when provided."""
    supplied = event.get("xg")
    if supplied is not None:
        return round(float(supplied), 4)
    if event.get("subtype") == "penalty" or event.get("type") in {"penalty_taken"}:
        return 0.76
    start = event.get("start") or event.get("end") or (event.get("frame") or {}).get("ball") or {}
    if not isinstance(start, dict) or start.get("x") is None or start.get("y") is None:
        return 0.0
    team = event.get("team_id")
    period = int(event.get("period", 1))
    attacks_right = ((team == "RED") == (period == 1))
    gx = 105.0 if attacks_right else 0.0
    gy = 34.0
    dx, dy = gx - float(start["x"]), gy - float(start["y"])
    distance = math.hypot(dx, dy)
    # Visible goal width is 7.32m. Angle is measured from the shot to the posts.
    post_y = (30.34, 37.66)
    angle = abs(math.atan2(post_y[1] - float(start["y"]), dx) - math.atan2(post_y[0] - float(start["y"]), dx))
    logit = 1.55 - 0.105 * distance + 1.25 * angle
    value = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit))))
    if event.get("body_part") == "head" or event.get("subtype") == "header":
        value *= 0.7
    return round(value, 4)
