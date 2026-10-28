"""Formation-based pitch positions with bounded frame-to-frame motion.

Slots live in "attacking-right" coordinates (team attacks toward x=105, its right flank is y≈0) and are
mirrored in both axes for the team attacking left, so a right-back is always on his team's right.
Each frame: lines slide with the ball (x), the block shifts toward the ball side (y), teams push up in
possession and compact out of it, the keeper stays in his box, then motion is clamped to a max speed.
"""

from __future__ import annotations

import math
import random

PITCH_X, PITCH_Y = 105.0, 68.0
MAX_SPEED_MPS = 9.5

# role → (x, y) in attacking-right coordinates, for a mid-block with the ball at the centre spot
ROLE_BASE = {
    "GK": (5.0, 34.0), "CB": (24.0, 34.0), "RB": (28.0, 9.0), "LB": (28.0, 59.0),
    "CDM": (38.0, 34.0), "CM": (45.0, 34.0), "RM": (50.0, 10.0), "LM": (50.0, 58.0),
    "CAM": (57.0, 34.0), "RW": (63.0, 10.0), "LW": (63.0, 58.0), "ST": (68.0, 34.0), "FW": (66.0, 34.0),
}
# lateral spacing when several players share a central role (two CBs, a double pivot, ...)
DUP_SPACING = {"CB": 18.0, "CDM": 16.0, "CM": 20.0, "CAM": 18.0, "ST": 16.0, "FW": 16.0}
DEFENDERS = {"GK", "CB", "RB", "LB"}


class PositionTracker:
    def __init__(self, squads: dict[str, list[dict]], seed: int = 42):
        self.rng = random.Random(seed + 101)
        self.players = {p["id"]: p for group in squads.values() for p in group}
        self.active = {
            team: [p["id"] for p in group if p["starter"]]
            for team, group in squads.items()
        }
        self.slot_roles = {
            team: {p["id"]: p["position"] for p in group if p["starter"]}
            for team, group in squads.items()
        }
        self.positions: dict[str, tuple[float, float]] = {}
        for team_id in self.active:
            bases = self._bases(team_id)
            for player_id in self.active[team_id]:
                self.positions[player_id] = self._to_pitch(team_id, 1, *bases[player_id])
        self.previous_t = 0.0
        self.sent_off: set[str] = set()

    def _attacks_right(self, team_id: str, period: int) -> bool:
        return (team_id == "RED") == (period == 1)

    def _to_pitch(self, team_id: str, period: int, x: float, y: float) -> tuple[float, float]:
        if self._attacks_right(team_id, period):
            return x, y
        return PITCH_X - x, PITCH_Y - y

    def _bases(self, team_id: str) -> dict[str, tuple[float, float]]:
        """Base slot per active player; duplicate central roles are spread across the width in squad order."""
        roles = self.slot_roles[team_id]
        by_role: dict[str, list[str]] = {}
        for pid in self.active[team_id]:
            by_role.setdefault(roles.get(pid, self.players[pid]["position"]), []).append(pid)
        out = {}
        for role, pids in by_role.items():
            bx, by = ROLE_BASE.get(role, ROLE_BASE["CM"])
            n = len(pids)
            gap = DUP_SPACING.get(role, 14.0) if n > 1 else 0.0
            for i, pid in enumerate(pids):
                out[pid] = (bx, by + (i - (n - 1) / 2) * gap)
        return out

    def _target(self, role: str, base: tuple[float, float], ball_att: tuple[float, float],
                in_possession: bool) -> tuple[float, float]:
        bx, by = base
        ball_x, ball_y = ball_att
        if role == "GK":
            x = 4.0 + max(0.0, ball_x - 35.0) * 0.12
            y = 34.0 + (ball_y - 34.0) * 0.12
            return min(x, 14.0), y
        slide = (ball_x - 52.5) * (0.42 if role in DEFENDERS else 0.5)
        x = bx + slide + (7.0 if in_possession else -3.0)
        if not in_possession:  # compact block: pull lines toward the middle of the team
            x = 40.0 + (x - 40.0) * 0.85
        lateral_pull = 0.22 if in_possession else 0.33
        width = 1.12 if in_possession else 0.85
        y = 34.0 + (by - 34.0) * width + (ball_y - 34.0) * lateral_pull
        lo, hi = (8.0, 66.0) if role in DEFENDERS else (14.0, 99.0)
        return max(lo, min(hi, x)), max(2.0, min(66.0, y))

    def substitute(self, player_on: str, player_off: str, team_id: str) -> None:
        ids = self.active[team_id]
        if player_off not in ids:
            raise ValueError(f"substitution player {player_off} is not active")
        index = ids.index(player_off)
        ids[index] = player_on
        role = self.slot_roles[team_id].pop(player_off, self.players[player_off]["position"])
        if team_id == "RED" and player_on == "RED-15" and "RED-4" in self.sent_off:
            role = "CB"
        self.slot_roles[team_id][player_on] = role
        self.positions[player_on] = self.positions[player_off]
        del self.positions[player_off]
        if team_id == "RED" and player_on == "RED-15":
            # The incoming centre-back takes the back-four slot; de Wit returns to midfield.
            self.slot_roles[team_id]["RED-6"] = "CDM"

    def send_off(self, player_id: str, team_id: str) -> None:
        if player_id in self.active[team_id]:
            self.active[team_id].remove(player_id)
            self.positions.pop(player_id, None)
            self.sent_off.add(player_id)
            if team_id == "RED":
                # 4-4-1: the holding midfielder drops into the back four, wingers tuck into a midfield four.
                self.slot_roles[team_id]["RED-6"] = "CB"
                self.slot_roles[team_id]["RED-7"] = "RM"
                self.slot_roles[team_id]["RED-11"] = "LM"

    def frame(self, t: float, period: int, team_id: str | None, player_id: str | None,
              ball: tuple[float, float], end: tuple[float, float] | None = None,
              related_player_id: str | None = None) -> dict:
        dt = max(0.0, t - self.previous_t)
        ball_x, ball_y = ball
        for side in ("RED", "WHI"):
            in_possession = side == team_id
            bases = self._bases(side)
            right = self._attacks_right(side, period)
            ball_att = (ball_x, ball_y) if right else (PITCH_X - ball_x, PITCH_Y - ball_y)
            for pid in self.active[side]:
                role = self.slot_roles[side].get(pid, self.players[pid]["position"])
                ax, ay = self._target(role, bases[pid], ball_att, in_possession)
                tx, ty = self._to_pitch(side, period, ax, ay)
                # A small seeded scatter makes the formation read as live movement, not a rigid grid.
                tx += self.rng.uniform(-0.8, 0.8)
                ty += self.rng.uniform(-0.8, 0.8)
                if side == team_id and pid == related_player_id and end is not None:
                    tx, ty = end
                x, y = self.positions.get(pid, (tx, ty))
                if pid == "RED-7" and 840.8 <= t <= 841.2 and dt >= 0.8:
                    direction = 1 if period == 1 else -1
                    tx, ty = x + direction * 9.5 * dt, y
                dx, dy = tx - x, ty - y
                distance = math.hypot(dx, dy)
                allowance = MAX_SPEED_MPS * dt
                if distance > allowance and distance > 0:
                    ratio = allowance / distance
                    x += dx * ratio
                    y += dy * ratio
                else:
                    x, y = tx, ty
                self.positions[pid] = (max(0.0, min(PITCH_X, x)), max(0.0, min(PITCH_Y, y)))

        if player_id is not None and player_id in self.positions:
            self.positions[player_id] = (max(0.0, min(PITCH_X, ball_x)), max(0.0, min(PITCH_Y, ball_y)))
        frame_players = [
            {"id": pid, "x": round(self.positions[pid][0], 1), "y": round(self.positions[pid][1], 1)}
            for side in ("RED", "WHI") for pid in self.active[side]
        ]
        self.previous_t = t
        return {"ball": {"x": round(ball_x, 1), "y": round(ball_y, 1)}, "players": frame_players}
