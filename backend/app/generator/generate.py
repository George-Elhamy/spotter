"""Generate Spotter's reproducible synthetic league and match data (seed 42)."""

from __future__ import annotations

import json
import random
from pathlib import Path

from .history import build_history
from .positions import PositionTracker
from .squads import TEAM_DATA, build_squads

SEED = 42
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PITCH_X, PITCH_Y = 105.0, 68.0


def _clock(minute: int, second: int = 0, added: int = 0) -> float:
    if minute <= 45:
        return minute * 60 + added * 60 + second
    return 2821 + (minute - 45 + added) * 60 + second


def _period(t: float) -> int:
    return 1 if t <= 2820 else 2


def _clock_fields(t: float) -> tuple[int, int, int, int]:
    if t <= 2820:
        raw_min = int(t // 60)
        return 1, min(45, raw_min), int(t % 60), max(0, raw_min - 45)
    elapsed = max(0.0, t - 2821)
    raw_min = 45 + int(elapsed // 60)
    return 2, min(90, raw_min), int(elapsed % 60), max(0, raw_min - 90)


def _event(team: str | None, player: str | None, kind: str, t: float, **kwargs) -> dict:
    period, minute, second, added = _clock_fields(t)
    event = {
        "id": 0, "t": round(float(t), 2), "period": period, "minute": minute,
        "second": second, "added": added, "type": kind, "subtype": None,
        "team_id": team, "player_id": player, "related_player_id": None,
        "start": None, "end": None, "outcome": None, "under_pressure": False,
        "body_part": None, "xg": None, "ball_speed_kmh": None, "flight_s": None,
        "restart": None, "card": None, "var": None, "frame": None,
    }
    event.update(kwargs)
    return event


def _active_at(team: str, t: float) -> list[str]:
    if team == "RED":
        ids = ["RED-1", "RED-2", "RED-4", "RED-5", "RED-3", "RED-6", "RED-8", "RED-14", "RED-7", "RED-9", "RED-11"]
        if t >= _clock(63):
            ids[ids.index("RED-14")] = "RED-15"
            ids[ids.index("RED-8")] = "RED-16"
        if t >= _clock(72):
            ids[ids.index("RED-11")] = "RED-19"
        if t >= _clock(85):
            ids[ids.index("RED-9")] = "RED-17"
        if t >= _clock(61):
            ids.remove("RED-4")
        return ids
    ids = ["WHI-1", "WHI-2", "WHI-5", "WHI-6", "WHI-3", "WHI-8", "WHI-18", "WHI-7", "WHI-10", "WHI-17", "WHI-9"]
    if t >= _clock(33, 45):
        ids[ids.index("WHI-5")] = "WHI-4"
    if t >= _clock(64):
        ids[ids.index("WHI-17")] = "WHI-11"
        ids[ids.index("WHI-18")] = "WHI-14"
        ids[ids.index("WHI-7")] = "WHI-16"
    return ids


def _script_events() -> list[dict]:
    events = [_event("RED", "RED-6", "kickoff", 0.0, restart="kickoff", end={"x": 54.0, "y": 34.0})]
    # Repeated Moretti/Whitaker duel pattern before the 15th minute.
    for minute in (4, 7, 10, 13):
        t = _clock(minute, 5)
        events.append(_event("RED", "RED-7", "dribble", t,
                             related_player_id="WHI-3", subtype="1v1", outcome="won",
                             under_pressure=True, end={"x": 61.0 + minute * 0.35, "y": 22.0 + minute * 0.7}))
    # The first high-speed frame pair is a real run, rather than an attribute-only label.
    events.append(_event("RED", "RED-7", "carry", 840.0, subtype="sprint", outcome="complete"))
    events.append(_event("RED", "RED-8", "carry", 841.0, subtype="sprint_tracking", outcome="complete"))

    t = _clock(9)
    events += [
        _event("WHI", "WHI-3", "foul", t, related_player_id="RED-7", outcome="foul"),
        _event("WHI", "WHI-3", "card", t + 1, related_player_id="RED-7", card="yellow"),
        _event("WHI", "WHI-8", "free_kick", t + 21, restart="free_kick", outcome="complete"),
    ]
    t = _clock(18, 5)
    events += [
        _event("RED", "RED-2", "pass", t - 7, related_player_id="RED-9", subtype="cross",
               outcome="complete", under_pressure=True, ball_speed_kmh=77.0, flight_s=1.1),
        _event("RED", "RED-9", "shot", t - 1, subtype="header", outcome="goal", body_part="head",
               xg=0.24, ball_speed_kmh=84.0, under_pressure=True),
        _event("RED", "RED-9", "goal", t, related_player_id="RED-2", subtype="header", outcome="goal"),
        _event("RED", "RED-6", "kickoff", t + 40, restart="kickoff"),
    ]
    # Goal is temporarily counted, then explicitly disallowed by VAR.
    t = _clock(27)
    events += [
        _event("RED", "RED-9", "shot", t - 3, subtype="header", outcome="goal", body_part="head",
               xg=0.31, ball_speed_kmh=88.0),
        _event("RED", "RED-9", "goal", t - 2, related_player_id="RED-2", outcome="goal"),
        _event(None, None, "var_check", t, subtype="offside"),
        _event(None, None, "var_decision", t + 2, var={"check": "offside", "decision": "goal_disallowed"}),
        _event("WHI", "WHI-1", "goal_kick", t + 60, restart="goal_kick"),
        _event("WHI", "WHI-1", "goal_kick", t + 60, restart="goal_kick"),
    ]
    t = _clock(33)
    events += [
        _event("WHI", "WHI-5", "injury", t, subtype="lower_leg", outcome="injury"),
        _event(None, None, "stoppage", t + 1, subtype="injury"),
        _event("WHI", "WHI-4", "substitution", t + 45, related_player_id="WHI-5", subtype="injury"),
        _event("WHI", "WHI-1", "goal_kick", t + 50, restart="goal_kick"),
    ]
    t = _clock(38, 12)
    events += [
        _event("WHI", "WHI-10", "pass", t - 8, related_player_id="WHI-9", subtype="through_ball",
               outcome="complete", under_pressure=True, ball_speed_kmh=82.0, flight_s=1.3,
               end={"x": 16.0, "y": 33.0}),
        _event("WHI", "WHI-9", "shot", t - 2, subtype="right_foot", outcome="goal", body_part="right_foot",
               xg=0.37, ball_speed_kmh=91.0, under_pressure=True),
        _event("WHI", "WHI-9", "goal", t, related_player_id="WHI-10", outcome="goal"),
        _event("RED", "RED-6", "kickoff", t + 40, restart="kickoff"),
    ]
    ht = _clock(45, 0, 2)
    events += [
        _event(None, None, "added_time", _clock(45), subtype="first_half", added=2),
        _event(None, None, "half_time", ht),
        _event("WHI", "WHI-18", "kickoff", ht + 1, restart="kickoff", end={"x": 51.0, "y": 34.0}),
    ]
    t = _clock(52)
    events += [
        _event("RED", "RED-4", "foul", t, related_player_id="WHI-9", outcome="foul"),
        _event("RED", "RED-4", "card", t + 1, related_player_id="WHI-9", card="yellow"),
        _event("WHI", "WHI-9", "penalty_awarded", t + 2, subtype="penalty", restart="penalty"),
        _event("WHI", "WHI-9", "penalty_taken", _clock(53), subtype="penalty", outcome="saved",
               body_part="right_foot", xg=0.76, ball_speed_kmh=104.0),
        _event("RED", "RED-1", "save", _clock(53) + 1, related_player_id="WHI-9", outcome="saved",
               body_part="hands"),
        _event("RED", "RED-5", "clearance", _clock(53) + 3, subtype="long_ball", outcome="complete"),
    ]
    t = _clock(61)
    events += [
        _event("RED", "RED-4", "foul", t, related_player_id="WHI-10", outcome="foul"),
        _event("RED", "RED-4", "card", t + 1, related_player_id="WHI-10", card="second_yellow"),
        _event("WHI", "WHI-8", "free_kick", t + 21, restart="free_kick"),
    ]
    t = _clock(63)
    events += [
        _event("RED", "RED-15", "substitution", t, related_player_id="RED-14"),
        _event("RED", "RED-16", "substitution", t + 2, related_player_id="RED-8"),
        _event("WHI", "WHI-11", "substitution", _clock(64), related_player_id="WHI-17"),
        _event("WHI", "WHI-14", "substitution", _clock(64) + 2, related_player_id="WHI-18"),
        _event("WHI", "WHI-16", "substitution", _clock(64) + 4, related_player_id="WHI-7"),
    ]
    t = _clock(67)
    events += [
        _event("WHI", "WHI-10", "pass", t - 6, related_player_id="WHI-11", subtype="through_ball",
               outcome="complete", under_pressure=True, ball_speed_kmh=79.0, flight_s=1.2),
        _event("WHI", "WHI-11", "shot", t - 1, subtype="right_foot", outcome="goal", body_part="right_foot",
               xg=0.29, ball_speed_kmh=96.0),
        _event("WHI", "WHI-11", "goal", t, related_player_id="WHI-10", outcome="goal"),
        _event("RED", "RED-6", "kickoff", t + 40, restart="kickoff"),
    ]
    events.append(_event("RED", "RED-19", "substitution", _clock(72), related_player_id="RED-11"))
    events += [
        _event("RED", "RED-7", "shot", _clock(79), subtype="left_foot", outcome="saved",
               body_part="left_foot", xg=0.18, ball_speed_kmh=86.0, under_pressure=True),
        _event("WHI", "WHI-10", "shot", _clock(81), subtype="right_foot", outcome="post", body_part="right_foot",
               xg=0.16, ball_speed_kmh=102.0),
        _event("RED", "RED-5", "block", _clock(81) + 2, outcome="blocked"),
        _event("WHI", "WHI-9", "shot", _clock(84), subtype="right_foot", outcome="blocked", body_part="right_foot",
               xg=0.41, ball_speed_kmh=89.0),
        _event("RED", "RED-5", "clearance", _clock(84) + 1, subtype="goal_line", outcome="won"),
        _event("RED", "RED-17", "substitution", _clock(85), related_player_id="RED-9"),
    ]
    t = _clock(88)
    events += [
        _event("RED", "RED-3", "pass", t - 5, related_player_id="RED-19", subtype="cross",
               outcome="complete", ball_speed_kmh=72.0, flight_s=1.0),
        _event("RED", "RED-19", "shot", t - 1, subtype="header", outcome="goal", body_part="head",
               xg=0.17, ball_speed_kmh=78.0),
        _event("RED", "RED-19", "goal", t, related_player_id="RED-3", outcome="goal"),
        _event("WHI", "WHI-1", "kickoff", t + 40, restart="kickoff"),
    ]
    events.append(_event(None, None, "added_time", _clock(90), subtype="second_half", added=6))
    t = _clock(90, 3, 3)
    events += [
        _event("RED", "RED-7", "dribble", t - 3, related_player_id="WHI-3", subtype="1v1",
               outcome="won", under_pressure=True),
        _event("RED", "RED-7", "shot", t - 1, subtype="right_foot", outcome="goal", body_part="right_foot",
               xg=0.33, ball_speed_kmh=93.0),
        _event("RED", "RED-7", "goal", t, related_player_id="RED-16", outcome="goal"),
    ]
    ft = _clock(90, 6, 6)
    events += [_event("WHI", "WHI-1", "kickoff", t + 40, restart="kickoff"),
               _event(None, None, "full_time", ft)]
    return events


def _phase_red_share(t: float) -> float:
    styles = {row["id"]: row["style"] for row in TEAM_DATA}
    red_style, whi_style = styles["RED"], styles["WHI"]
    base = red_style["possession"] / (red_style["possession"] + whi_style["possession"])
    if t < 900:
        return min(0.74, base + 0.12)
    if 1500 <= t <= 2220:
        return max(0.34, 0.43 - (whi_style["press"] - 0.5) * 0.14)
    if 4680 <= t <= 5160:
        return 0.50
    if t > _clock(61):
        return max(0.34, base - 0.17)
    if t < 2820:
        return min(0.6, base - 0.09)
    return max(0.45, base - 0.05)


def _generic_events(seed: int, squads: dict[str, list[dict]], anchors: list[dict]) -> list[dict]:
    rng = random.Random(seed)
    player_data = {player["id"]: player for roster in squads.values() for player in roster}
    styles = {row["id"]: row["style"] for row in TEAM_DATA}

    def pick_player(ids: list[str], attribute: str) -> str:
        weights = [max(1, player_data[pid]["attrs"][attribute]) for pid in ids]
        return rng.choices(ids, weights=weights)[0]

    anchor_times = [event["t"] for event in anchors]
    entries: list[dict] = []
    desired_passes = {"RED": 550, "WHI": 590}
    for team, count in desired_passes.items():
        made = 0
        while made < count:
            t = rng.uniform(5.0, 5860.0)
            if any(abs(t - at) < 2.7 for at in anchor_times):
                continue
            probability = _phase_red_share(t)
            if (team == "RED" and rng.random() > probability) or (team == "WHI" and rng.random() > 1 - probability):
                continue
            players = _active_at(team, t)
            receivers = [pid for pid in players if pid != ("RED-1" if team == "RED" else "WHI-1")]
            actor = pick_player([pid for pid in players if not pid.endswith("-1")], "passing")
            receiver = rng.choice([pid for pid in receivers if pid != actor])
            complete = rng.random() < 0.84
            directness = styles[team]["directness"]
            subtype = rng.choices(["short", "long_ball", "through_ball", "cross", "cutback", "switch"],
                                  weights=[60 - directness * 24, 10 + directness * 18, 9 + directness * 7,
                                           9 + directness * 5, 6, 6 + directness * 8])[0]
            entries.append(_event(team, actor, "pass", t, related_player_id=receiver,
                                  subtype=subtype, outcome="complete" if complete else "incomplete",
                                  under_pressure=rng.random() < (0.20 if t < 900 else
                                      min(0.8, styles[team]["press"] * 0.72) if 1500 <= t <= 2220 else
                                      styles[team]["press"] * 0.49),
                                  ball_speed_kmh=round(rng.uniform(44, 79), 1),
                                  flight_s=round(rng.uniform(0.6, 2.3), 1)))
            made += 1
    # Add enough open-play attempts to keep both sides within the specified shot range.
    for team, count in (("RED", 13), ("WHI", 14)):
        made = 0
        while made < count:
            t = rng.uniform(900, 5830)
            if any(abs(t - at) < 3.2 for at in anchor_times):
                continue
            actor = pick_player([pid for pid in _active_at(team, t) if not pid.endswith("-1")], "finishing")
            outcome = rng.choices(["saved", "off_target", "blocked"], [0.42, 0.34, 0.24])[0]
            entries.append(_event(team, actor, "shot", t, subtype=rng.choice(["right_foot", "left_foot", "header"]),
                                  outcome=outcome, body_part=rng.choice(["right_foot", "left_foot", "head"]),
                                  xg=round(rng.uniform(0.03, 0.38), 3),
                                  ball_speed_kmh=round(rng.uniform(60, 120), 1),
                                  under_pressure=rng.random() < 0.48))
            made += 1
    fillers = ["carry", "dribble", "duel", "tackle", "interception", "clearance", "block", "foul",
               "save", "corner", "throw_in", "goal_kick", "offside", "free_kick"]
    weights = [16, 8, 8, 9, 8, 7, 5, 6, 3, 0.7, 2.5, 1.5, 2, 1.5]
    for _ in range(900):
        t = rng.uniform(8, 5840)
        if any(abs(t - at) < 2.4 for at in anchor_times):
            continue
        red_share = _phase_red_share(t)
        team = "RED" if rng.random() < red_share else "WHI"
        players = _active_at(team, t)
        kind = rng.choices(fillers, weights)[0]
        if t < 900 and kind == "foul":
            kind = "carry"
        attribute = "dribbling" if kind == "dribble" else "defending" if kind in {"tackle", "interception", "block", "clearance"} else "passing"
        actor = pick_player([pid for pid in players if not pid.endswith("-1")], attribute)
        opponent = "WHI" if team == "RED" else "RED"
        defender = rng.choice([pid for pid in _active_at(opponent, t) if not pid.endswith("-1")])
        data = {}
        if kind == "dribble":
            data.update(related_player_id=defender, outcome=rng.choice(["won", "lost"]), under_pressure=True)
        elif kind == "duel":
            data.update(related_player_id=defender, outcome=rng.choice(["won", "lost"]))
        elif kind == "tackle":
            data.update(related_player_id=defender, outcome="won")
        elif kind == "foul":
            data.update(related_player_id=defender, outcome="foul")
        elif kind in {"carry", "interception", "clearance", "block", "offside", "save"}:
            data.update(outcome={"carry": "complete", "interception": "won", "clearance": "won",
                                 "block": "blocked", "offside": "offside", "save": "saved"}[kind])
        elif kind in {"corner", "throw_in", "goal_kick", "free_kick"}:
            data.update(restart=kind, outcome="complete")
        entries.append(_event(team, actor, kind, t, **data))
    # Scripted stoppages are quiet windows: suppress open play until their restart resumes.
    quiet_windows: list[tuple[float, float]] = []
    for event in anchors:
        t, kind = event["t"], event["type"]
        if kind == "goal":
            var_after = any(row["type"] == "var_decision" and t < row["t"] < t + 75 for row in anchors)
            if not var_after:
                restart = next((row["t"] for row in anchors if row["type"] == "kickoff" and row["t"] > t), t + 40)
                quiet_windows.append((t + 0.5, restart - 0.1))
        elif kind == "var_check":
            restart = next((row["t"] for row in anchors if row.get("restart") == "goal_kick" and row["t"] > t), t + 60)
            quiet_windows.append((t + 2.1, restart - 0.1))
        elif kind == "injury":
            sub = next((row["t"] for row in anchors if row["type"] == "substitution" and row.get("subtype") == "injury" and row["t"] > t), t + 45)
            quiet_windows.append((t + 1.1, sub - 0.1))
        elif kind == "card":
            restart = next((row["t"] for row in anchors if row.get("restart") is not None and row["t"] > t), t + 20)
            quiet_windows.append((t + 1.1, restart - 0.1))
        elif kind == "penalty_awarded":
            taken = next((row["t"] for row in anchors if row["type"] == "penalty_taken" and row["t"] > t), t + 60)
            quiet_windows.append((t + 0.1, taken - 0.1))
    subs = sorted(row["t"] for row in anchors if row["type"] == "substitution")
    for sub_t in subs:
        later_nearby = [t for t in subs if sub_t <= t <= sub_t + 90]
        if sub_t == max(later_nearby):
            quiet_windows.append((sub_t + 0.1, sub_t + 25.0))
    entries = [entry for entry in entries if not any(start < entry["t"] < end for start, end in quiet_windows)]
    # Generic restarts are preceded by their dead-ball pause; thin nearby open play
    # rather than moving script anchors or allowing play to continue through the setup.
    restart_pause = {"throw_in": 6.0, "goal_kick": 8.0, "free_kick": 12.0, "corner": 15.0}
    dropped: set[int] = set()
    kept_restarts: list[dict] = []
    for restart_event in sorted((e for e in entries if e.get("restart") in restart_pause), key=lambda e: e["t"]):
        window_start = restart_event["t"] - restart_pause[restart_event["restart"]]
        blocked_by_anchor = any(window_start < anchor["t"] < restart_event["t"] for anchor in anchors)
        blocked_by_restart = any(window_start < previous["t"] < restart_event["t"] for previous in kept_restarts)
        if blocked_by_anchor or blocked_by_restart:
            dropped.add(id(restart_event))
            continue
        kept_restarts.append(restart_event)
        for candidate in entries:
            if candidate is not restart_event and window_start < candidate["t"] < restart_event["t"]:
                dropped.add(id(candidate))
    entries = [entry for entry in entries if id(entry) not in dropped]
    return entries


def _decorate_positions(events: list[dict], squads: dict[str, list[dict]]) -> list[dict]:
    tracker = PositionTracker(squads, SEED)
    # Stable team-specific player metadata used to choose natural start/end locations.
    actor_attrs = {p["id"]: p["attrs"] for group in squads.values() for p in group}
    last_ball = (52.5, 34.0)
    for event in events:
        t, team, actor = event["t"], event["team_id"], event["player_id"]
        kind = event["type"]
        if kind == "substitution":
            tracker.substitute(actor, event["related_player_id"], team)
        if kind == "card" and event.get("card") == "second_yellow":
            # Keep the player on the pitch for the dismissal event's own frame.
            pass
        if event.get("start") is not None:
            start = (float(event["start"]["x"]), float(event["start"]["y"]))
        elif actor is not None and actor in tracker.positions:
            start = tracker.positions[actor]
        else:
            start = last_ball
        start = (max(1.0, min(104.0, start[0])), max(1.0, min(67.0, start[1])))
        direction = 1 if ((team == "RED") == (event["period"] == 1)) else -1
        if (kind == "pass" and actor == "WHI-10" and event.get("subtype") == "through_ball"
                and event["period"] == 1 and 37 <= event["minute"] <= 39):
            # Novak releases it from deep (~29 m out) so the assist is a genuinely difficult through ball.
            start = (45.0, max(24.0, min(44.0, start[1])))
            event["start"] = {"x": start[0], "y": round(start[1], 1)}
            end = (16.0, start[1])
        elif event.get("end") is not None:
            end = (float(event["end"]["x"]), float(event["end"]["y"]))
        elif kind == "shot" or kind == "penalty_taken":
            end = (104.0 if direction > 0 else 1.0, max(23.0, min(45.0, 34.0 + (start[1] - 34.0) * 0.15)))
        elif kind == "pass":
            forward = 29.0 if event.get("subtype") == "through_ball" else 12.0 if event.get("subtype") == "long_ball" else 5.0
            receiver_pos = tracker.positions.get(event.get("related_player_id"), (start[0] + direction * forward, start[1]))
            if event.get("subtype") in {"through_ball", "long_ball", "cross", "switch"}:
                end = (start[0] + direction * forward, receiver_pos[1])
            else:
                end = (receiver_pos[0], receiver_pos[1])
        elif kind == "dribble" or kind == "carry":
            end = (start[0] + direction * 4.5, start[1] + 1.2)
        else:
            end = start
        end = (round(max(0.0, min(PITCH_X, end[0])), 1), round(max(0.0, min(PITCH_Y, end[1])), 1))
        if event.get("start") is None:
            event["start"] = {"x": round(start[0], 1), "y": round(start[1], 1)}
        event["end"] = {"x": end[0], "y": end[1]}
        if kind == "pass" and event.get("outcome") == "complete":
            # Crosses and through-balls finish in attacking danger; regular passes are shorter.
            event["under_pressure"] = bool(event.get("under_pressure"))
        frame = tracker.frame(t, event["period"], team, actor, start, end if kind == "pass" else None,
                              event.get("related_player_id") if kind == "pass" else None)
        event["frame"] = frame
        last_ball = end
        if kind == "card" and event.get("card") == "second_yellow":
            tracker.send_off(actor, team)
    for index, event in enumerate(events, 1):
        event["id"] = index
    return events


def build_match_events(squads: dict[str, list[dict]]) -> dict:
    anchors = _script_events()
    generated = _generic_events(SEED, squads, anchors)
    events = sorted([*anchors, *generated], key=lambda row: (row["t"], row["type"], row["player_id"] or ""))
    # Do not leave generated duplicate timestamps after rounding.
    for index in range(1, len(events)):
        if events[index]["t"] <= events[index - 1]["t"]:
            events[index]["t"] = round(events[index - 1]["t"] + 0.01, 2)
    events = _decorate_positions(events, squads)
    kickoff2 = next(e["t"] for e in events if e["type"] == "kickoff" and e["t"] > 2800)
    halftime = next(e["t"] for e in events if e["type"] == "half_time")
    fulltime = next(e["t"] for e in events if e["type"] == "full_time")
    final_whi = next(e for e in events if e["type"] == "goal" and e["team_id"] == "WHI" and e["t"] > 3900)
    return {
        "meta": {
            "seed": SEED,
            "period_start_t": {"1": 0.0, "2": kickoff2},
            "half_time_t": halftime, "full_time_t": fulltime,
            "lineups": {team: [p["id"] for p in group if p["starter"]] for team, group in squads.items()},
            "final_score": [3, 2],
            "attack_direction": {"1": {"RED": "+x", "WHI": "-x"},
                                 "2": {"RED": "-x", "WHI": "+x"}},
            "mid_match_score": [1, 1], "score_at_67": [1, 2],
        },
        "events": events,
    }


def _write_json(path: Path, value, compact: bool = False) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        if compact:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def generate() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    squads = build_squads()
    history, dossiers, squads = build_history(SEED)
    match_events = build_match_events(squads)
    _write_json(DATA_DIR / "teams.json", {"teams": TEAM_DATA})
    _write_json(DATA_DIR / "squads.json", squads)
    _write_json(DATA_DIR / "league_history.json", history)
    _write_json(DATA_DIR / "dossiers.json", dossiers)
    _write_json(DATA_DIR / "match_events.json", match_events, compact=True)
    print(f"Generated 5 JSON files in {DATA_DIR}")
    print(f"Match stream: {len(match_events['events'])} events; final t={match_events['meta']['full_time_t']:.2f}s")


if __name__ == "__main__":
    generate()
