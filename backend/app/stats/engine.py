"""Incremental, seekable match statistics for Spotter.

The full fixture is retained only as an input sequence. All public query methods
read `_history`, which contains events already ingested (never future events).
Ingest updates frame motion, possession, score, active-player time, and alerts in
one pass; richer window queries fold only the selected ingested events.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import alerts as alert_module
from .control_chaos import chaos_index
from .pass_difficulty import attack_sign, pass_difficulty
from .quiet import quiet_window as get_quiet_window
from .xg import expected_goals

TEAMS = ("RED", "WHI")
ON_BALL = {"pass", "carry", "dribble", "shot", "goal"}
STATS_KEYS = (
    "passes", "passes_completed", "pass_accuracy", "avg_pass_difficulty", "hardest_pass",
    "key_passes", "progressive_passes", "shots", "shots_on_target", "goals", "assists", "xg",
    "dribbles_attempted", "dribbles_won", "tackles", "interceptions", "clearances", "duels_won",
    "fouls", "cards", "touches", "distance_km", "top_speed_kmh", "sprints", "minutes_played",
)


class StatsEngine:
    """Consumes an ordered event fixture incrementally."""

    # Public to agent prompts: keys are intended to remain concise and factual.
    METRICS = {
        "passes": "Completed and attempted passes by a player or team.",
        "passes_completed": "Completed passes by a player.",
        "pass_accuracy": "Completed passes as a percentage of attempts.",
        "accuracy": "Team pass completion percentage.",
        "avg_pass_difficulty": "Mean 0–100 difficulty score of a player's passes.",
        "hardest_pass": "The player's highest-scoring pass and its event id.",
        "key_passes": "Passes directly creating an attempt or explicitly tagged key.",
        "progressive_passes": "Passes advancing at least ten metres toward goal.",
        "shots": "Shots attempted.", "shots_on_target": "Shots on target, including goals.",
        "on target": "Team shots on target, including goals.",
        "goals": "Goals scored by the player/team.", "assists": "Recorded assists on goals.",
        "xg": "Expected goals from shots, summed over the selected window.",
        "dribbles_attempted": "One-versus-one dribbles attempted.", "dribbles_won": "Successful dribbles.",
        "tackles": "Tackles attempted.", "interceptions": "Interceptions made.",
        "clearances": "Clearances made.", "duels_won": "Duels won.", "fouls": "Fouls committed.",
        "cards": "Cards received.", "touches": "On-ball event involvements.",
        "distance_km": "Estimated distance covered in kilometres from position-frame movement.",
        "top_speed_kmh": "Highest observed frame-to-frame speed.", "sprints": "Entries into speeds of at least 25 km/h.",
        "minutes_played": "Estimated minutes on the pitch.", "possession": "Time-weighted possession share.",
        "turnovers": "Possessions lost by failed on-ball or duel actions.",
        "final_third_entries": "Actions entering the attacking final third.", "corners": "Corners won or taken.",
        "ppda": "Opponent passes allowed per defensive action in the pressing zone.",
        "territory": "Share of team events in the opponent half.", "control_index": "Rolling control index, 0–100.",
        "chaos_index": "Rolling match chaos index, 0–100.", "pass_difficulty": "Difficulty score for a pass event (0–100).",
        "ball_speed_kmh": "Ball speed recorded on an event.", "score": "Current score difference for a team or match.",
        "dribbles_won_vs": "Successful dribbles by a player against the specified opponent.",
        "duels_won_vs": "Duels won by a player against the specified opponent.",
        "tackles_vs": "Tackles by a player against the specified opponent.",
    }

    def __init__(self, events: list[dict], squads: dict, meta: dict):
        self._events = sorted(events, key=lambda e: (float(e.get("t", 0)), e.get("id", 0)))
        self.squads = squads or {}
        self.meta = meta or {}
        self.players = {p["id"]: p for team in self.squads.values() for p in team if isinstance(p, dict) and p.get("id")}
        self._dossiers = self._load_dossiers()
        self.reset()

    def _load_dossiers(self) -> dict:
        path = Path(__file__).resolve().parents[1] / "data" / "dossiers.json"
        try:
            return json.loads(path.read_text()).get("players", {})
        except (OSError, json.JSONDecodeError, AttributeError):
            return {}

    @property
    def t(self) -> float:
        return self._t

    def reset(self) -> None:
        self._history: list[dict] = []
        self._history_ids: set[Any] = set()
        self._t = 0.0
        self._alerts: list[dict] = []
        self._possession_team: str | None = None
        self._possession_since: float | None = None
        self._possession_segments: list[tuple[float, float, str]] = []
        self._possession_seconds = defaultdict(float)
        self._last_frame: dict[str, tuple[float, float, float]] = {}
        self._distance_m = defaultdict(float)
        self._top_speed = defaultdict(float)
        self._sprints = defaultdict(int)
        self._active_players = self._initial_active()
        self._played_seconds = defaultdict(float)
        self._score = {"RED": 0, "WHI": 0}
        self._disallowed_goals: set[Any] = set()
        self._last_event: dict | None = None
        self._pass_counts = defaultdict(int)
        self._hardest_pass = defaultdict(float)
        self._duel_records: list[dict] = []
        self._subbed_off: set[str] = set()
        self._sent_off: set[str] = set()
        self._distance_milestones: set[tuple[str, int]] = set()
        self._speed_alerted: set[str] = set()
        self._season_best_alerted: set[str] = set()

    def _initial_active(self) -> set[str]:
        lineups = self.meta.get("lineups", {})
        if isinstance(lineups, dict) and lineups:
            return {pid for ids in lineups.values() for pid in (ids or [])}
        return {p["id"] for p in self.players.values() if p.get("starter")}

    def ingest(self, event: dict) -> list[dict]:
        if event is None:
            return []
        event_id = event.get("id")
        if event_id is not None and event_id in self._history_ids:
            return []
        e = event
        t = float(e.get("t", self._t))
        if self._last_event and t < self._t:
            raise ValueError("events must be ingested in non-decreasing t order")
        self._advance_minutes(e, t)
        self._advance_possession(e, t)
        self._advance_frames(e, t)
        self._apply_event(e)
        self._history.append(e)
        if event_id is not None:
            self._history_ids.add(event_id)
        self._t = t
        self._last_event = e
        fresh = alert_module.alert(self, e)
        self._alerts.extend(fresh)
        if e.get("type") == "pass" and e.get("player_id"):
            difficulty = pass_difficulty(e, self.meta)
            if difficulty is not None:
                self._hardest_pass[e["player_id"]] = max(self._hardest_pass[e["player_id"]], difficulty)
        return fresh

    def _advance_minutes(self, e: dict, t: float) -> None:
        previous = self._last_event
        if not previous or previous.get("period") != e.get("period"):
            return
        elapsed = max(0.0, t - float(previous.get("t", t)))
        # A long pause may be the half-time break or a dead segment; count at most
        # 45 minutes per period so half-time cannot inflate player minutes.
        if elapsed > 20 * 60:
            elapsed = 0.0
        for pid in self._active_players:
            self._played_seconds[pid] += elapsed

    def _advance_possession(self, e: dict, t: float) -> None:
        typ = e.get("type")
        if typ not in ON_BALL or e.get("team_id") not in TEAMS:
            return
        team = e["team_id"]
        if self._possession_team is None:
            self._possession_team, self._possession_since = team, t
        elif team != self._possession_team:
            start = float(self._possession_since if self._possession_since is not None else t)
            if t > start:
                self._possession_segments.append((start, t, self._possession_team))
                self._possession_seconds[self._possession_team] += t - start
            self._possession_team, self._possession_since = team, t

    def _advance_frames(self, e: dict, t: float) -> None:
        if self._last_event and self._last_event.get("period") != e.get("period"):
            self._last_frame.clear()
        players = ((e.get("frame") or {}).get("players") or [])
        current_ids = set()
        # Frames are sampled at event cadence. Comparing the generated full-match
        # frame totals with the spec's 9–12 km outfielder target gives this
        # fixture-wide sparse-sampling correction (not player-specific tuning).
        sampling_correction = 1.4
        for row in players:
            pid = row.get("id")
            if not pid or row.get("x") is None or row.get("y") is None:
                continue
            current_ids.add(pid)
            old = self._last_frame.get(pid)
            point = (float(row["x"]), float(row["y"]))
            if old:
                old_t, old_x, old_y = old
                dt = t - old_t
                if 0.8 <= dt <= 20.0:
                    distance = math.dist((old_x, old_y), point)
                    speed = distance / dt * 3.6
                    self._distance_m[pid] += distance * sampling_correction
                    if speed > self._top_speed[pid]:
                        self._top_speed[pid] = speed
                    if speed >= 25.0 and self._top_speed[pid] < 25.0:
                        self._sprints[pid] += 1
                    elif speed >= 25.0:
                        # Count only entries into sprint speed, inferred from the previous frame speed.
                        last_speed = self._last_frame.get(f"speed:{pid}", (0.0, 0.0, 0.0))[1]
                        if last_speed < 25.0:
                            self._sprints[pid] += 1
                    self._last_frame[f"speed:{pid}"] = (t, speed, 0.0)
                elif dt > 20.0:
                    self._last_frame.pop(f"speed:{pid}", None)
            self._last_frame[pid] = (t, point[0], point[1])
        # Retire absent players so a returning substitute cannot be joined across time off-pitch.
        for pid in set(k for k in self._last_frame if not k.startswith("speed:")) - current_ids:
            self._last_frame.pop(pid, None)
            self._last_frame.pop(f"speed:{pid}", None)

    def _apply_event(self, e: dict) -> None:
        typ, pid, team = e.get("type"), e.get("player_id"), e.get("team_id")
        if typ == "pass" and pid:
            self._pass_counts[pid] += 1
        if typ == "goal" and team in TEAMS:
            self._score[team] += 1
        elif typ == "var_decision" and (e.get("var") or {}).get("decision") == "goal_disallowed":
            explicit_goal_id = e.get("related_event_id") or (e.get("var") or {}).get("event_id")
            latest_goal = next((x for x in reversed(self._history)
                                if x.get("type") == "goal" and x.get("id") not in self._disallowed_goals
                                and (explicit_goal_id is None or x.get("id") == explicit_goal_id)), None)
            if latest_goal:
                goal_id = latest_goal.get("id")
                self._disallowed_goals.add(goal_id)
                goal_team = latest_goal.get("team_id")
                if goal_team in TEAMS:
                    self._score[goal_team] = max(0, self._score[goal_team] - 1)
                self._alerts = [a for a in self._alerts if not (a.get("event_id") == goal_id and
                                a.get("kind") in {"first_goal", "first_league_goal"})]
        if typ == "substitution":
            incoming = pid
            outgoing = e.get("related_player_id") or e.get("player_off_id")
            if outgoing:
                self._active_players.discard(outgoing)
                self._subbed_off.add(outgoing)
            if incoming:
                self._active_players.add(incoming)
        if typ == "card" and e.get("card") in {"red", "second_yellow"} and pid:
            self._active_players.discard(pid)
            self._sent_off.add(pid)
        self._record_duel(e)

    def _record_duel(self, e: dict) -> None:
        typ = e.get("type")
        if typ not in {"dribble", "duel", "tackle", "interception"}:
            return
        actor, opponent = e.get("player_id"), e.get("related_player_id") or e.get("opponent_id")
        if not actor or not opponent:
            return
        won = e.get("outcome") in {"won", "complete", "successful", "success"}
        self._duel_records.append({"event": e, "actor": actor, "opponent": opponent,
                                  "kind": typ, "won": won})

    def rebuild(self, upto_t: float) -> None:
        self.reset()
        for event in self._events:
            if float(event.get("t", 0)) > upto_t:
                break
            self.ingest(event)

    def _window_events(self, window: str = "match") -> list[dict]:
        if window == "match":
            return self._history
        if window in {"5min", "10min"}:
            span = 300.0 if window == "5min" else 600.0
            cutoff = self._t - span
            return [e for e in self._history if float(e.get("t", 0)) >= cutoff]
        if window == "half":
            period = self._last_event.get("period") if self._last_event else 1
            return [e for e in self._history if e.get("period") == period]
        raise ValueError(f"unsupported stats window: {window}")

    def _name(self, player_id: str | None) -> str:
        return (self.players.get(player_id or "", {}).get("short_name") or
                self.players.get(player_id or "", {}).get("name") or player_id or "")

    def player_stats(self, player_id: str, window: str = "match") -> dict:
        events = self._window_events(window)
        own = [e for e in events if e.get("player_id") == player_id]
        passes = [e for e in own if e.get("type") == "pass"]
        completed = [e for e in passes if e.get("outcome") in {"complete", "completed", "success", "successful"}]
        difficulties = [(e, pass_difficulty(e, self.meta)) for e in passes]
        difficulties = [(e, v) for e, v in difficulties if v is not None]
        hardest = max(difficulties, key=lambda item: item[1], default=None)
        shots = [e for e in own if e.get("type") in {"shot", "penalty_taken"}]
        goals = [e for e in own if e.get("type") == "goal" and e.get("id") not in self._disallowed_goals]
        on_target = [e for e in shots if e.get("outcome") in {"goal", "saved", "on_target"}]
        keypass_ids = self._key_pass_event_ids(events)
        keypasses = [e for e in passes if e.get("id") in keypass_ids]
        dribbles = [e for e in own if e.get("type") == "dribble"]
        duels_won = sum(1 for r in self._duel_records if r["actor"] == player_id and r["kind"] == "duel" and r["won"]
                        and r["event"] in events)
        types = [e.get("type") for e in own]
        xg_total = sum(expected_goals(e, self.meta) for e in shots)
        if window == "match":
            distance = self._distance_m[player_id] / 1000.0
            speed = self._top_speed[player_id]
            sprints = self._sprints[player_id]
            mins = self._played_seconds[player_id] / 60.0
        else:
            selected = {id(e) for e in events}
            # Frame movement belongs to the later event in each pair.
            relevant_frames = [e for e in events if e.get("frame")]
            distance, speed, sprints = self._motion_for(player_id, relevant_frames)
            mins = self._minutes_for(player_id, events)
        return {
            "player_id": player_id, "name": self._name(player_id),
            "passes": len(passes), "passes_completed": len(completed),
            "pass_accuracy": round(100.0 * len(completed) / len(passes), 1) if passes else 0.0,
            "avg_pass_difficulty": round(statistics.mean(v for _, v in difficulties), 2) if difficulties else 0.0,
            "hardest_pass": ({"event_id": hardest[0].get("id"), "difficulty": round(hardest[1], 2)} if hardest else None),
            "key_passes": len(keypasses), "progressive_passes": sum(self._is_progressive(e) for e in passes),
            "shots": len(shots), "shots_on_target": len(on_target), "goals": len(goals),
            "assists": sum(1 for e in events if e.get("type") == "goal" and e.get("id") not in self._disallowed_goals
                           and e.get("related_player_id") == player_id),
            "xg": round(xg_total, 3), "dribbles_attempted": len(dribbles),
            "dribbles_won": sum(1 for e in dribbles if e.get("outcome") in {"won", "complete", "successful", "success"}),
            "tackles": types.count("tackle"), "interceptions": types.count("interception"),
            "clearances": types.count("clearance"), "duels_won": duels_won,
            "fouls": types.count("foul"), "cards": types.count("card"),
            "touches": sum(1 for e in events if e.get("player_id") == player_id and e.get("type") in ON_BALL),
            "distance_km": round(distance, 2), "top_speed_kmh": round(speed, 1), "sprints": sprints,
            "minutes_played": round(mins, 1),
        }

    def _is_progressive(self, event: dict) -> bool:
        start, end = event.get("start") or {}, event.get("end") or {}
        if start.get("x") is None or end.get("x") is None:
            return False
        sign = attack_sign(self.meta, event.get("period", 1), event.get("team_id"))
        return (float(end["x"]) - float(start["x"])) * sign >= 10.0

    @staticmethod
    def _key_pass_event_ids(events: list[dict]) -> set[Any]:
        result = set()
        possession_team = None
        last_pass = None
        for event in events:
            if event.get("type") not in ON_BALL or event.get("team_id") not in TEAMS:
                if event.get("type") == "pass" and (event.get("key_pass") or event.get("is_key_pass")
                                                       or event.get("subtype") == "key_pass"):
                    result.add(event.get("id"))
                continue
            team = event.get("team_id")
            if team != possession_team:
                possession_team, last_pass = team, None
            if event.get("type") == "pass":
                if event.get("key_pass") or event.get("is_key_pass") or event.get("subtype") == "key_pass":
                    result.add(event.get("id"))
                last_pass = event
            elif event.get("type") == "shot":
                if (last_pass and (not last_pass.get("related_player_id")
                                   or last_pass.get("related_player_id") == event.get("player_id"))):
                    result.add(last_pass.get("id"))
                last_pass = None
        return result

    def _motion_for(self, pid: str, events: list[dict]) -> tuple[float, float, int]:
        previous = None
        distance, speed, sprints = 0.0, 0.0, 0
        prior_speed = 0.0
        for event in events:
            row = next((p for p in ((event.get("frame") or {}).get("players") or []) if p.get("id") == pid), None)
            if not row:
                previous, prior_speed = None, 0.0
                continue
            t, x, y = float(event.get("t", 0)), float(row["x"]), float(row["y"])
            if previous:
                dt = t - previous[0]
                if 0.8 <= dt <= 20.0:
                    d = math.dist((x, y), (previous[1], previous[2]))
                    v = d / dt * 3.6
                    distance += d * 1.4
                    speed = max(speed, v)
                    if v >= 25 and prior_speed < 25:
                        sprints += 1
                    prior_speed = v
                else:
                    prior_speed = 0.0
            previous = (t, x, y)
        return distance / 1000, speed, sprints

    def _minutes_for(self, player_id: str, events: list[dict]) -> float:
        total = 0.0
        previous = None
        active = set(self._initial_active())
        for e in events:
            t = float(e.get("t", 0))
            if previous and previous.get("period") == e.get("period") and player_id in active:
                dt = max(0.0, t - float(previous.get("t", t)))
                if dt <= 1200:
                    total += dt
            if e.get("type") == "substitution":
                if e.get("related_player_id"):
                    active.discard(e["related_player_id"])
                if e.get("player_id"):
                    active.add(e["player_id"])
            if e.get("type") == "card" and e.get("card") in {"red", "second_yellow"}:
                active.discard(e.get("player_id"))
            previous = e
        return total / 60.0

    def team_stats(self, team: str, window: str = "match") -> dict:
        if team not in TEAMS:
            raise ValueError(f"unknown team {team}")
        events = self._window_events(window)
        own = [e for e in events if e.get("team_id") == team]
        passes = [e for e in own if e.get("type") == "pass"]
        completed = [e for e in passes if e.get("outcome") in {"complete", "completed", "success", "successful"}]
        shots = [e for e in own if e.get("type") in {"shot", "penalty_taken"}]
        possession = self._possession_share_for_events(events)
        own_poss = possession[0 if team == "RED" else 1]
        difficulties = [pass_difficulty(e, self.meta) for e in passes]
        difficulties = [v for v in difficulties if v is not None]
        opponent_actions = sum(1 for e in events if e.get("team_id") != team and e.get("type") in {"tackle", "interception", "foul", "duel"})
        opponent_passes = sum(1 for e in events if e.get("team_id") != team and e.get("type") == "pass")
        territorial_events = [e for e in own if (e.get("start") or (e.get("frame") or {}).get("ball") or {}).get("x") is not None]
        in_opp_half = sum(1 for e in territorial_events if self._in_opponent_half(e, team))
        final_entries = sum(1 for e in own if self._enters_final_third(e, team))
        xg_sum = sum(expected_goals(e, self.meta) for e in shots)
        return {
            "team_id": team, "passes": len(passes), "accuracy": round(100 * len(completed) / len(passes), 1) if passes else 0.0,
            "possession": round(own_poss, 1), "shots": len(shots),
            "on target": sum(1 for e in shots if e.get("outcome") in {"goal", "saved", "on_target"}),
            "xg": round(xg_sum, 3), "corners": sum(1 for e in own if e.get("type") == "corner" or e.get("restart") == "corner"),
            "fouls": sum(1 for e in own if e.get("type") == "foul"), "cards": sum(1 for e in own if e.get("type") == "card"),
            "turnovers": sum(1 for e in own if e.get("outcome") in {"incomplete", "lost", "failed", "turnover"}),
            "final_third_entries": final_entries,
            "avg_pass_difficulty": round(statistics.mean(difficulties), 2) if difficulties else 0.0,
            "ppda": round(opponent_passes / opponent_actions, 2) if opponent_actions else 0.0,
            "territory": round(100 * in_opp_half / len(territorial_events), 1) if territorial_events else 0.0,
        }

    def _in_opponent_half(self, event: dict, team: str) -> bool:
        point = event.get("start") or (event.get("frame") or {}).get("ball") or {}
        x = point.get("x")
        if x is None:
            return False
        sign = attack_sign(self.meta, event.get("period", 1), team)
        return float(x) * sign > 52.5 if sign > 0 else 105.0 - float(x) > 52.5

    def _enters_final_third(self, event: dict, team: str) -> bool:
        start, end = event.get("start") or {}, event.get("end") or {}
        if start.get("x") is None or end.get("x") is None:
            return False
        sign = attack_sign(self.meta, event.get("period", 1), team)
        a = float(start["x"]) if sign > 0 else 105.0 - float(start["x"])
        b = float(end["x"]) if sign > 0 else 105.0 - float(end["x"])
        return a < 70 <= b

    def _possession_share(self, window: str = "match") -> tuple[float, float]:
        if not self._history:
            return 50.0, 50.0
        if window in {"5min", "10min"}:
            low = max(0.0, self._t - (300 if window == "5min" else 600))
        elif window == "half":
            period = self._last_event.get("period", 1)
            half_events = [e for e in self._history if e.get("period") == period]
            low = float(half_events[0].get("t", 0)) if half_events else self._t
        else:
            low = float(self._history[0].get("t", 0))
        seconds = defaultdict(float)
        segments = list(self._possession_segments)
        if self._possession_team is not None and self._possession_since is not None:
            segments.append((self._possession_since, self._t, self._possession_team))
        for start, end, team in segments:
            duration = max(0.0, min(end, self._t) - max(start, low))
            if team in TEAMS:
                seconds[team] += duration
        total = seconds["RED"] + seconds["WHI"]
        if total == 0:
            counts = defaultdict(int)
            for e in self._window_events(window):
                if e.get("type") in ON_BALL and e.get("team_id") in TEAMS:
                    counts[e["team_id"]] += 1
            count_total = counts["RED"] + counts["WHI"]
            if count_total == 0:
                return 50.0, 50.0
            return 100 * counts["RED"] / count_total, 100 * counts["WHI"] / count_total
        return 100 * seconds["RED"] / total, 100 * seconds["WHI"] / total

    def _control_values(self, events: list[dict]) -> dict[str, float]:
        possession = self._possession_share_for_events(events)
        totals = {}
        for team in TEAMS:
            own = [e for e in events if e.get("team_id") == team]
            territory = [e for e in own if (e.get("start") or (e.get("frame") or {}).get("ball") or {}).get("x") is not None]
            territory_share = sum(self._in_opponent_half(e, team) for e in territory) / len(territory) if territory else 0.5
            passes = [e for e in own if e.get("type") == "pass"]
            completion = sum(e.get("outcome") in {"complete", "completed", "success", "successful"} for e in passes) / len(passes) if passes else 0.5
            xg = sum(expected_goals(e, self.meta) for e in own if e.get("type") in {"shot", "penalty_taken"})
            totals[team] = (possession[0 if team == "RED" else 1], territory_share, completion, xg)
        # Four equally weighted normalized components; normalize each matchup component.
        parts = []
        for idx in range(4):
            red, white = totals["RED"][idx], totals["WHI"][idx]
            if idx == 0:
                parts.append((red / 100, white / 100))
            elif red + white > 0:
                parts.append((red / (red + white), white / (red + white)))
            else:
                parts.append((0.5, 0.5))
        # Possession and territory are the leading live-control signals. Passing
        # reliability contributes context; xG contributes a smaller finishing-
        # chance signal so one isolated big chance cannot swamp a sustained press.
        weights = (0.45, 0.35, 0.15, 0.05)
        red_score = sum(pair[0] * weight for pair, weight in zip(parts, weights))
        return {"RED": red_score * 100, "WHI": (1 - red_score) * 100}

    def _possession_share_for_events(self, events: list[dict]) -> tuple[float, float]:
        durations = defaultdict(float)
        last_team, last_t = None, None
        counts = defaultdict(int)
        for e in events:
            if e.get("type") not in ON_BALL or e.get("team_id") not in TEAMS:
                continue
            team, t = e["team_id"], float(e.get("t", 0))
            counts[team] += 1
            if last_team is not None and last_t is not None and t >= last_t:
                durations[last_team] += t - last_t
            last_team, last_t = team, t
        total = durations["RED"] + durations["WHI"]
        if total <= 0:
            total = counts["RED"] + counts["WHI"]
            return ((100 * counts["RED"] / total, 100 * counts["WHI"] / total) if total else (50.0, 50.0))
        return 100 * durations["RED"] / total, 100 * durations["WHI"] / total

    def snapshot(self) -> dict:
        control = self._control_values(self._window_events("5min"))
        poss_r, poss_w = self._possession_share("match")
        roll_r, roll_w = self._possession_share("5min")
        win = self.win_probability()
        red_control = int(round(control["RED"]))
        match_red_possession = round(poss_r, 1)
        rolling_red_possession = round(roll_r, 1)
        return {
            "control": {"RED": red_control, "WHI": 100 - red_control},
            "chaos": self._chaos_for_window(self._window_events("5min")),
            "possession": {"match": {"RED": match_red_possession, "WHI": round(100 - match_red_possession, 1)},
                           "rolling": {"RED": rolling_red_possession, "WHI": round(100 - rolling_red_possession, 1)}},
            "win_prob": {k: round(v, 3) for k, v in win.items() if k != "inputs"},
        }

    def quiet_window(self, event: dict) -> float | None:
        return get_quiet_window(event)

    def match_leaders(self, metric: str, n: int = 5) -> list[dict]:
        if metric not in STATS_KEYS:
            return []
        rows = []
        for pid, player in self.players.items():
            stats = self.player_stats(pid)
            value = stats.get(metric)
            if isinstance(value, dict):
                value = (value or {}).get("difficulty", 0)
            rows.append({"player_id": pid, "name": self._name(pid), "team_id": player.get("team_id"), "value": value})
        return sorted(rows, key=lambda r: (r["value"] if isinstance(r["value"], (int, float)) else 0, r["player_id"]), reverse=True)[:n]

    def alerts_since(self, since_t: float) -> list[dict]:
        return [a for a in self._alerts if float(a["t"]) >= since_t]

    def _chaos_for_window(self, events: list[dict]) -> int:
        if len(events) < 2:
            return 0
        duration = min(300.0, max(1.0, float(events[-1].get("t", 0)) - float(events[0].get("t", 0))))
        rolling = chaos_index(events, duration)
        # A 2.5-minute sub-window lets the index react when a hectic spell starts, instead of lagging 5 minutes.
        cutoff = float(events[-1].get("t", 0)) - 150.0
        recent = [e for e in events if float(e.get("t", 0)) >= cutoff]
        if len(recent) < 2 or duration < 150.0:
            return rolling
        return max(rolling, chaos_index(recent, 150.0))

    def control_chaos(self, window: str = "5min") -> dict:
        events = self._window_events(window)
        control = self._control_values(events)
        low_t = max(0.0, self._t - 900.0)
        by_minute = defaultdict(list)
        for e in self._history:
            t = float(e.get("t", 0))
            if t >= low_t:
                by_minute[int(t // 60)].append(e)
        timeline = []
        for minute in sorted(by_minute):
            es = by_minute[minute]
            minute_control = self._control_values(es)
            red_control = round(minute_control["RED"])
            timeline.append({"minute": minute, "chaos": self._chaos_for_window(es),
                             "control": {"RED": red_control, "WHI": 100 - red_control}})
        red_control = round(control["RED"])
        return {"control": {"RED": red_control, "WHI": 100 - red_control}, "chaos": self._chaos_for_window(events),
                "timeline": timeline}

    def compare_periods(self, a: str, b: str) -> dict:
        def parse(spec: str) -> tuple[int, int]:
            match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", spec)
            if not match:
                raise ValueError("period must be a minute range like '0-15'")
            return int(match.group(1)), int(match.group(2))
        def select(spec: str) -> list[dict]:
            lo, hi = parse(spec)
            return [e for e in self._history if lo <= int(e.get("minute", 0)) <= hi]
        def period_stats(spec: str) -> dict:
            events = select(spec)
            result = {team: self._team_stats_for_events(team, events) for team in TEAMS}
            result["control"] = self._control_values(events)
            return result
        return {a: period_stats(a), b: period_stats(b)}

    def _team_stats_for_events(self, team: str, events: list[dict]) -> dict:
        saved = self._history, self._t
        # Centralize team aggregation while ensuring interval-specific filtering.
        self._history = events
        if events:
            self._t = float(events[-1].get("t", 0))
        try:
            return self.team_stats(team, "match")
        finally:
            self._history, self._t = saved

    def pressure(self, team: str, window: str = "5min") -> dict:
        events = self._window_events(window)
        own = [e for e in events if e.get("team_id") == team]
        pressures = sum(bool(e.get("under_pressure")) for e in own)
        defensive = [e for e in events if e.get("team_id") != team and e.get("type") in {"pass", "carry", "dribble"}]
        ppda_actions = sum(1 for e in events if e.get("team_id") == team and e.get("type") in {"tackle", "interception", "foul"} and self._in_opponent_half(e, team))
        allowed = sum(1 for e in defensive if self._in_opponent_half(e, team))
        losses = sum(1 for e in own if e.get("outcome") in {"incomplete", "lost", "failed", "turnover"})
        high_regains = sum(1 for e in events if e.get("team_id") == team and e.get("type") in {"tackle", "interception"} and self._in_opponent_half(e, team))
        return {"team_id": team, "pressures": pressures, "ppda": round(allowed / ppda_actions, 2) if ppda_actions else 0.0,
                "turnovers_forced": sum(1 for e in events if e.get("team_id") != team and e.get("outcome") in {"incomplete", "lost", "failed", "turnover"}),
                "high_regains": high_regains, "turnovers": losses}

    def average_shape(self, team: str, window: str = "5min") -> dict:
        frames = [e.get("frame", {}).get("players", []) for e in self._window_events(window) if e.get("frame")]
        samples = defaultdict(list)
        for frame in frames:
            for player in frame:
                if str(player.get("id", "")).startswith(team + "-"):
                    samples[player["id"]].append((float(player["x"]), float(player["y"])))
        positions = {pid: {"x": round(statistics.mean(p[0] for p in ps), 1), "y": round(statistics.mean(p[1] for p in ps), 1)}
                     for pid, ps in samples.items()}
        xs = [p["x"] for p in positions.values()]
        ys = [p["y"] for p in positions.values()]
        sign = attack_sign(self.meta, self._last_event.get("period", 1) if self._last_event else 1, team)
        positions = {pid: {"name": self._name(pid), **point} for pid, point in positions.items()}
        return {"team_id": team, "players": positions,
                "defensive_line_height": round(statistics.mean(sorted(xs, reverse=sign < 0)[:4]), 1) if xs else 0.0,
                "width": round(max(ys) - min(ys), 1) if ys else 0.0,
                "compactness": round(statistics.pstdev(xs), 1) if len(xs) > 1 else 0.0}

    def player_matchup(self, a: str, b: str) -> dict:
        relevant = [r for r in self._duel_records if {r["actor"], r["opponent"]} == {a, b}]
        attempts = len(relevant)
        won_by_a = sum(1 for r in relevant if r["actor"] == a and r["won"])
        won_by_b = sum(1 for r in relevant if r["actor"] == b and r["won"])
        dribbles = [r for r in relevant if r["kind"] == "dribble"]
        tackles = [r for r in relevant if r["kind"] == "tackle"]
        return {"a": a, "b": b, "a_name": self._name(a), "b_name": self._name(b),
                "attempts": attempts, "won_by_a": won_by_a, "won_by_b": won_by_b,
                "dribbles_attempted": len(dribbles), "dribbles_won_by_a": sum(r["actor"] == a and r["won"] for r in dribbles),
                "dribbles_won_by_b": sum(r["actor"] == b and r["won"] for r in dribbles),
                "tackles_by_a": sum(r["actor"] == a for r in tackles), "tackles_by_b": sum(r["actor"] == b for r in tackles),
                "event_ids": [r["event"].get("id") for r in relevant]}

    def duels(self, a: str, b: str) -> dict:
        return self.player_matchup(a, b)

    def win_probability(self) -> dict:
        # Time left is inferred from fixture duration when available; capped to regulation + added time.
        # Never inspect future fixture events from a query. The match clock baseline
        # is 90 minutes plus the six minutes of added time in the canonical fixture.
        total_duration = 96 * 60.0
        remaining = max(0.0, total_duration - self._t)
        score_diff = self._score["RED"] - self._score["WHI"]
        men = {team: sum(pid.startswith(team + "-") for pid in self._active_players) for team in TEAMS}
        recent = self._window_events("5min")
        xg = {team: sum(expected_goals(e, self.meta) for e in recent if e.get("team_id") == team and e.get("type") in {"shot", "penalty_taken"}) for team in TEAMS}
        rate_diff = (xg["RED"] - xg["WHI"]) / 5.0
        # Logistic score margin with shrinking time horizon, numerical bounds included.
        horizon = max(0.12, math.sqrt(max(remaining, 1.0) / 5400.0))
        logit = (1.35 * score_diff + 0.16 * (men["RED"] - men["WHI"]) + 0.22 * rate_diff) / horizon
        p_red_win = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit))))
        draw_weight = math.exp(-1.2 * abs(score_diff) - 0.10 * abs(men["RED"] - men["WHI"]))
        p_draw = max(0.01, min(0.85, draw_weight * (0.46 if remaining > 0 else 0.04)))
        p_red = (1.0 - p_draw) * p_red_win
        p_white = (1.0 - p_draw) * (1.0 - p_red_win)
        denom = p_red + p_draw + p_white
        p_red = round(p_red / denom, 3)
        p_draw = round(p_draw / denom, 3)
        p_white = round(1.0 - p_red - p_draw, 3)
        return {"RED": p_red, "DRAW": p_draw, "WHI": p_white,
                "inputs": {"score": dict(self._score), "score_diff": score_diff, "seconds_remaining": round(remaining, 1),
                           "players_on_pitch": men, "rolling_5min_xg": {k: round(v, 3) for k, v in xg.items()}}}

    def key_moments(self) -> list[dict]:
        result = []
        for e in self._history:
            typ = e.get("type")
            var = e.get("var") or {}
            is_big_chance = typ in {"shot", "penalty_taken"} and (expected_goals(e, self.meta) >= 0.25 or e.get("big_chance"))
            if typ not in {"goal", "card", "var_check", "var_decision", "penalty_awarded", "penalty_taken", "substitution", "injury"} and not is_big_chance:
                continue
            rescinded = typ == "goal" and e.get("id") in self._disallowed_goals
            result.append({"t": e.get("t", 0), "minute": e.get("minute", 0), "added": e.get("added", 0),
                           "type": "big_chance" if is_big_chance else ("goal_disallowed" if rescinded else typ),
                           "player_id": e.get("player_id"),
                           "text": "Goal disallowed by VAR" if rescinded else self._moment_text(e, var),
                           "event_id": e.get("id")})
        return result

    def _moment_text(self, event: dict, var: dict) -> str:
        typ = event.get("type")
        if typ == "goal": return f"{self._name(event.get('player_id'))} scored"
        if typ == "card": return f"{event.get('card', 'card').replace('_', ' ')} for {self._name(event.get('player_id'))}"
        if typ in {"var_check", "var_decision"}: return f"VAR {var.get('decision') or var.get('check') or 'review'}"
        if typ == "substitution": return f"{self._name(event.get('player_id'))} substituted on"
        return typ.replace("_", " ")

    def player_timeline(self, player_id: str) -> list[dict]:
        important = {"shot", "card", "goal", "substitution"}
        keypass_ids = self._key_pass_event_ids(self._history)
        result = []
        for e in self._history:
            if e.get("player_id") != player_id:
                continue
            keypass = e.get("type") == "pass" and e.get("id") in keypass_ids
            dribble_won = e.get("type") == "dribble" and e.get("outcome") in {"won", "complete", "successful", "success"}
            if e.get("type") not in important and not keypass and not dribble_won:
                continue
            result.append({"t": e.get("t", 0), "minute": e.get("minute", 0), "type": e.get("type"),
                           "event_id": e.get("id"), "related_player_id": e.get("related_player_id")})
        return result

    def recent_involvement(self, since_t: float) -> dict:
        events = [e for e in self._history if float(e.get("t", 0)) >= since_t]
        ids = []
        for e in events:
            if e.get("player_id") and e.get("type") in ON_BALL | {"tackle", "duel", "dribble", "interception"}:
                ids.append(e["player_id"])
            if e.get("related_player_id") and e.get("type") in {"pass", "tackle", "duel", "dribble"}:
                ids.append(e["related_player_id"])
        last_on_ball = next((e for e in reversed(events) if e.get("type") in ON_BALL), None)
        location = (last_on_ball or {}).get("end") or (last_on_ball or {}).get("start") or {}
        team = (last_on_ball or {}).get("team_id")
        return {"player_ids": list(dict.fromkeys(ids)), "team_in_possession": team,
                "final_third": bool(last_on_ball and location.get("x") is not None and team and
                                    (float(location["x"]) * attack_sign(self.meta, last_on_ball.get("period", 1), team) >= 70
                                     if attack_sign(self.meta, last_on_ball.get("period", 1), team) > 0
                                     else 105 - float(location["x"]) >= 70))}

    def metric_value(self, entity: str, metric: str, window: str = "match", against: str | None = None) -> float | None:
        if metric in {"control_index", "chaos_index"}:
            if entity not in TEAMS and entity != "match": return None
            control = self._control_values(self._window_events(window))
            if metric == "control_index": return round(control[entity], 2) if entity in TEAMS else None
            return float(self._chaos_for_window(self._window_events(window)))
        if metric == "possession":
            if entity == "match": return 100.0
            if entity not in TEAMS: return None
            return round(self._possession_share(window)[0 if entity == "RED" else 1], 2)
        if metric in {"pass_difficulty", "ball_speed_kmh"}:
            event = next((e for e in self._history if str(e.get("id")) == str(entity)), None)
            if not event: return None
            if metric == "pass_difficulty": return pass_difficulty(event, self.meta) if event.get("type") == "pass" else None
            value = event.get("ball_speed_kmh")
            return float(value) if value is not None else None
        if metric == "score":
            if entity == "match": return float(sum(self._score.values()))
            if entity in TEAMS: return float(self._score[entity])
            return None
        if metric in {"dribbles_won_vs", "duels_won_vs", "tackles_vs"}:
            if not against: return None
            relevant_type = {"dribbles_won_vs": "dribble", "duels_won_vs": "duel", "tackles_vs": "tackle"}[metric]
            return float(sum(r["actor"] == entity and r["opponent"] == against and r["kind"] == relevant_type and r["won"]
                             and r["event"] in self._window_events(window) for r in self._duel_records))
        if entity in TEAMS:
            stats = self.team_stats(entity, window)
            aliases = {"pass_accuracy": "accuracy", "shots_on_target": "on target"}
            value = stats.get(aliases.get(metric, metric))
            return float(value) if isinstance(value, (int, float)) else None
        if entity in self.players:
            stats = self.player_stats(entity, window)
            value = stats.get(metric)
            if isinstance(value, dict):
                value = value.get("difficulty")
            return float(value) if isinstance(value, (int, float)) else None
        return None

    def _alerts_for_event(self, e: dict) -> list[dict]:
        result = []
        pid, team, t = e.get("player_id"), e.get("team_id"), float(e.get("t", self._t))
        def add(kind: str, metric: str, value: float, text: str) -> None:
            result.append({"t": t, "kind": kind, "player_id": pid, "team_id": team, "metric": metric,
                           "value": round(value, 2), "text": text, "event_id": e.get("id")})
        if pid and self._top_speed[pid] > 33 and pid not in self._speed_alerted:
            self._speed_alerted.add(pid)
            add("top_speed", "top_speed_kmh", self._top_speed[pid], f"{self._name(pid)} exceeded 33 km/h")
        season_speed = self._dossiers.get(pid, {}).get("top_speed_kmh") if pid else None
        if pid and season_speed is not None and self._top_speed[pid] > float(season_speed) and pid not in self._season_best_alerted:
            self._season_best_alerted.add(pid)
            add("season_best", "top_speed_kmh", self._top_speed[pid], f"{self._name(pid)} set a season-best speed")
        if e.get("type") in {"shot", "penalty_taken"} and float(e.get("ball_speed_kmh") or 0) > 100:
            add("shot_speed", "ball_speed_kmh", float(e["ball_speed_kmh"]), f"Shot speed topped 100 km/h")
        for runner, distance in self._distance_m.items():
            for milestone in (5000, 10000):
                key = (runner, milestone)
                if distance >= milestone and key not in self._distance_milestones:
                    self._distance_milestones.add(key)
                    result.append({"t": t, "kind": "distance_milestone", "player_id": runner,
                                   "team_id": self.players.get(runner, {}).get("team_id"), "metric": "distance_km",
                                   "value": milestone / 1000.0,
                                   "text": f"{self._name(runner)} covered {milestone // 1000} km", "event_id": e.get("id")})
        if e.get("type") == "goal":
            if sum(self._score.values()) == 1:
                add("first_goal", "goals", 1, "First goal of the match")
            dossier = self._dossiers.get(pid, {})
            if dossier.get("goals", dossier.get("league_goals", 1)) == 0:
                add("first_league_goal", "goals", 1, f"{self._name(pid)} scored a first league goal")
        if e.get("type") == "pass" and pid:
            count = self._pass_counts[pid]
            if count in {50, 100}:
                add("pass_milestone", "passes", float(count), f"{self._name(pid)} attempted {count} passes")
            difficulty = pass_difficulty(e, self.meta)
            if difficulty is not None and difficulty > 85 and difficulty > self._hardest_pass[pid]:
                add("hardest_pass", "pass_difficulty", difficulty, f"{self._name(pid)} attempted their hardest pass so far")
        return result

def _calibration_report(engine: StatsEngine) -> str:
    lines = ["Chaos by match minute (0–95):"]
    sampler = StatsEngine(engine._events, engine.squads, engine.meta)
    event_index = 0
    for minute in range(96):
        sample_t = minute * 60.0
        while event_index < len(engine._events) and float(engine._events[event_index].get("t", 0)) <= sample_t:
            sampler.ingest(engine._events[event_index])
            event_index += 1
        value = sampler._chaos_for_window(sampler._window_events("5min"))
        lines.append(f"{minute:02d}: {value:3d}")
    lines.append("Control by five-minute window:")
    for start in range(0, 96, 5):
        events = [e for e in engine._history if start * 60 <= float(e.get("t", 0)) < (start + 5) * 60]
        if events:
            values = engine._control_values(events)
            lines.append(f"{start:02d}-{min(start + 5, 96):02d}: RED {values['RED']:.1f} / WHI {values['WHI']:.1f}")
    return "\n".join(lines)


if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parents[1] / "data"
    match = json.loads((data_dir / "match_events.json").read_text())
    squads = json.loads((data_dir / "squads.json").read_text())
    engine = StatsEngine(match["events"], squads, match.get("meta", {}))
    engine.rebuild(float("inf"))
    print(_calibration_report(engine))
