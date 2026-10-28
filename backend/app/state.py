"""MatchData (static generated files) and MatchState (live, shared; spec §3)."""
from __future__ import annotations

import bisect
import json
from dataclasses import dataclass, field
from typing import Any

from . import config, llm
from .models import AGENTS, Directive, InstanceSettings

JUMP_PRESETS = [0, 8, 17, 26, 37, 51, 60, 66, 80, 87, 90]


def _load(name: str) -> Any:
    return json.loads((config.DATA_DIR / name).read_text())


class MatchData:
    def __init__(self) -> None:
        self.teams_raw = _load("teams.json")["teams"]
        self.teams = {t["id"]: t for t in self.teams_raw}
        self.squads: dict[str, list[dict]] = _load("squads.json")
        self.players = {p["id"]: p for team in ("RED", "WHI") for p in self.squads[team]}
        self.history = _load("league_history.json")
        self.dossiers = _load("dossiers.json")
        m = _load("match_events.json")
        self.meta = m["meta"]
        self.events: list[dict] = m["events"]
        self.event_ts = [e["t"] for e in self.events]
        self.by_id = {e["id"]: e for e in self.events}
        self.duration_t = self.events[-1]["t"]

    def name(self, pid: str | None) -> str:
        p = self.players.get(pid or "")
        return p["short_name"] if p else (pid or "")

    def index_at(self, t: float) -> int:
        """Index of the first event with e.t > t."""
        return bisect.bisect_right(self.event_ts, t)

    def seek_t(self, minute: float) -> float:
        """Match t for a jump preset minute (0 = kickoff; 45+ means 2nd half)."""
        if minute <= 0:
            return 0.0
        period = 1 if minute < 45 else 2
        for e in self.events:
            if e["period"] == period and e["minute"] >= minute:
                return max(0.0, e["t"] - 1.0)
        return self.duration_t

    def key_moments(self) -> list[dict]:
        out = []
        for e in self.events:
            label = None
            if e["type"] == "goal":
                label = f"GOAL {self.name(e['player_id'])}"
            elif e["type"] == "card":
                label = f"{(e.get('card') or 'card').replace('_', ' ')} {self.name(e['player_id'])}"
            elif e["type"] == "var_decision":
                label = "VAR decision"
            elif e["type"] in ("penalty_awarded", "injury"):
                label = f"{e['type'].replace('_', ' ')}"
            elif e["type"] == "substitution":
                label = f"Sub: {self.name(e['player_id'])} on"
            if label:
                out.append({"t": e["t"], "minute": e["minute"], "added": e.get("added", 0), "label": label})
        return out

    def meta_payload(self) -> dict:
        def team(tid: str) -> dict:
            t = self.teams[tid]
            return {k: t.get(k) for k in ("id", "name", "short_name", "color_primary", "color_secondary",
                                          "formation", "manager", "stadium")}

        players = [{"id": p["id"], "team_id": p["team_id"], "number": p["number"], "name": p["name"],
                    "short_name": p["short_name"], "position": p["position"], "nationality": p["nationality"],
                    "starter": p["starter"]} for p in self.players.values()]
        return {"teams": {"RED": team("RED"), "WHI": team("WHI")}, "players": players,
                "jump_presets": [{"minute": m, "label": f"{m}'"} for m in JUMP_PRESETS],
                "key_moments": self.key_moments(), "moment_presets": self.moment_presets(),
                "duration_t": self.duration_t}

    def moment_presets(self, lead_s: float = 15.0) -> list[dict]:
        """Jump targets 15 s before each big moment, so the build-up and the call are both on screen."""
        out = []
        for e in self.events:
            label = None
            if e["type"] == "goal":
                ruled_out = any(n["type"] == "var_decision" and 0 < n["t"] - e["t"] < 180 for n in self.events)
                label = f"Goal · {self.name(e['player_id'])}" + (" (ruled out by VAR)" if ruled_out else "")
            elif e["type"] == "penalty_awarded":
                label = "Penalty"
            elif e["type"] == "card" and e.get("card") in ("second_yellow", "red"):
                label = f"Red card · {self.name(e['player_id'])}"
            if label:
                when = f"{e['minute']}'+{e['added']}" if e.get("added") else f"{e['minute']}'"
                out.append({"t": round(max(0.0, e["t"] - lead_s), 1), "label": f"{when} {label}"})
        return out


@dataclass
class MatchState:
    """Live state rebuilt from events up to the server clock. Tools and agents read this."""
    data: MatchData
    t: float = 0.0
    next_idx: int = 0
    period: int = 1
    score: list[int] = field(default_factory=lambda: [0, 0])
    goals: list[dict] = field(default_factory=list)  # goal events still standing
    on_pitch: set[str] = field(default_factory=set)
    last_event: dict | None = None
    instance: InstanceSettings = field(default_factory=InstanceSettings)
    agent_status: dict[str, dict] = field(default_factory=lambda: {a: {"status": "idle", "last_ms": None} for a in AGENTS})
    spoken: list[str] = field(default_factory=list)  # last spoken lines (Caller "don't reuse")
    cost_cap_reached: bool = False

    def reset(self) -> None:
        self.t, self.next_idx, self.period = 0.0, 0, 1
        self.score, self.goals, self.last_event, self.spoken = [0, 0], [], None, []
        self.on_pitch = set(self.data.meta["lineups"]["RED"]) | set(self.data.meta["lineups"]["WHI"])

    def apply(self, e: dict) -> None:
        self.last_event = e
        self.period = e["period"]
        typ = e["type"]
        if typ == "goal":
            self.goals.append(e)
            self.score[0 if e["team_id"] == "RED" else 1] += 1
        elif typ == "var_decision" and (e.get("var") or {}).get("decision") == "goal_disallowed" and self.goals:
            g = self.goals.pop()
            self.score[0 if g["team_id"] == "RED" else 1] -= 1
        elif typ == "substitution":
            self.on_pitch.discard(e.get("related_player_id") or "")
            if e.get("player_id"):
                self.on_pitch.add(e["player_id"])
        elif typ == "card" and e.get("card") in ("second_yellow", "red"):
            self.on_pitch.discard(e.get("player_id") or "")

    @property
    def directives(self) -> list[Directive]:
        return self.instance.directives

    def clock_msg(self, speed: float, paused: bool) -> dict:
        return {"type": "clock", "t": round(self.t, 2), "display_delay_s": config.DISPLAY_DELAY_S, "speed": speed,
                "period": self.period, "score": list(self.score), "paused": paused,
                "cost_cap_reached": self.cost_cap_reached, "cost_usd": round(llm.ledger.total, 4),
                "cost_cap_usd": config.COST_CAP_USD}

    def match_time_label(self, e: dict | None = None) -> str:
        e = e or self.last_event
        if not e:
            return "0'"
        return f"{e['minute']}'+{e['added']}" if e.get("added") else f"{e['minute']}'"
