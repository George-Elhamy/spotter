"""Pass-difficulty scoring helpers (Spotter spec §6)."""
from __future__ import annotations

import math
from typing import Any


def _xy(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict) or value.get("x") is None or value.get("y") is None:
        return None
    return float(value["x"]), float(value["y"])


def attack_sign(meta: dict, period: int | str, team: str) -> int:
    """Return +1 when the team attacks toward x=105 and -1 when toward x=0."""
    directions = meta.get("attack_direction", {})
    period_data = directions.get(str(period), directions.get(period, {})) if isinstance(directions, dict) else {}
    value = period_data.get(team) if isinstance(period_data, dict) else None
    if isinstance(value, (int, float)):
        return 1 if value >= 0 else -1
    if isinstance(value, str):
        normalized = value.lower()
        if normalized in {"right", "+x", "positive", "east", "105"}:
            return 1
        if normalized in {"left", "-x", "negative", "west", "0"}:
            return -1
    # The canonical match script switches direction at half time.
    return 1 if ((team == "RED") == (int(period) == 1)) else -1


def pass_difficulty(event: dict, meta: dict) -> float | None:
    start, end = _xy(event.get("start")), _xy(event.get("end"))
    team = event.get("team_id")
    if not start or not end or team not in {"RED", "WHI"}:
        return None
    period = event.get("period", 1)
    sign = attack_sign(meta, period, team)
    distance = math.dist(start, end)
    progress = max(0.0, (end[0] - start[0]) * sign)
    players = ((event.get("frame") or {}).get("players") or [])
    pressure_count = 0
    bypassed = 0
    for player in players:
        if player.get("id") == event.get("player_id"):
            continue
        px, py = player.get("x"), player.get("y")
        if px is None or py is None:
            continue
        opponent = str(player.get("id", "")).startswith("WHI-" if team == "RED" else "RED-")
        if opponent and math.hypot(float(px) - end[0], float(py) - end[1]) <= 3.0:
            pressure_count += 1
        if opponent and min(start[0], end[0]) < float(px) < max(start[0], end[0]):
            if (float(px) - start[0]) * sign > 0 and (end[0] - float(px)) * sign > 0:
                bypassed += 1
    pressure = (0.5 if event.get("under_pressure") else 0.0) + 0.5 * min(pressure_count / 3.0, 1.0)
    attacking_end_x = end[0] * sign if sign > 0 else 105.0 - end[0]
    final_third = attacking_end_x >= 70.0
    # Penalty area on a 105x68 pitch (16.5m deep, 40.32m wide).
    in_box = attacking_end_x >= 88.5 and 13.84 <= end[1] <= 54.16
    target_zone = 1.0 if in_box else (0.5 if final_third else 0.0)
    score = (
        25.0 * min(distance / 45.0, 1.0)
        + 25.0 * min(progress / 30.0, 1.0)
        + 20.0 * min(pressure, 1.0)
        + 20.0 * min(bypassed / 4.0, 1.0)
        + 10.0 * target_zone
    )
    return round(min(100.0, max(0.0, score)), 2)
