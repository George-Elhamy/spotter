"""Validate generated Spotter data against the match, roster and realism contract."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .positions import MAX_SPEED_MPS, PITCH_X, PITCH_Y

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EVENT_KEYS = {
    "id", "t", "period", "minute", "second", "added", "type", "subtype", "team_id",
    "player_id", "related_player_id", "start", "end", "outcome", "under_pressure",
    "body_part", "xg", "ball_speed_kmh", "flight_s", "restart", "card", "var", "frame",
}
EVENT_TYPES = {
    "kickoff", "pass", "carry", "dribble", "shot", "save", "goal", "tackle", "interception",
    "clearance", "block", "duel", "foul", "card", "free_kick", "corner", "throw_in", "goal_kick",
    "offside", "var_check", "var_decision", "penalty_awarded", "penalty_taken", "injury", "stoppage",
    "substitution", "added_time", "half_time", "full_time",
}
LINE_SUM_FIELDS = (
    "goals", "assists", "shots", "key_passes", "dribbles_won", "tackles", "yellow", "red",
    "penalties_faced", "penalties_saved", "sub_goals",
)


def _load(name: str):
    with (DATA_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _league_table(matchdays: list[dict]) -> list[dict]:
    team_ids = {team for md in matchdays for result in md["results"] for team in (result["home"], result["away"])}
    rows = {team: {"team_id": team, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "gd": 0, "pts": 0}
            for team in team_ids}
    for md in matchdays:
        for result in md["results"]:
            home, away = rows[result["home"]], rows[result["away"]]
            hg, ag = result["home_goals"], result["away_goals"]
            home["p"] += 1; away["p"] += 1
            home["gf"] += hg; home["ga"] += ag
            away["gf"] += ag; away["ga"] += hg
            if hg > ag:
                home["w"] += 1; home["pts"] += 3; away["l"] += 1
            elif ag > hg:
                away["w"] += 1; away["pts"] += 3; home["l"] += 1
            else:
                home["d"] += 1; away["d"] += 1; home["pts"] += 1; away["pts"] += 1
    for row in rows.values():
        row["gd"] = row["gf"] - row["ga"]
    ranked = sorted(rows.values(), key=lambda row: (-row["pts"], -row["gd"], -row["gf"], row["team_id"]))
    for position, row in enumerate(ranked, 1):
        row["position"] = position
    return ranked


def _validate_history(squads: dict, history: dict, dossiers: dict) -> None:
    matchdays = history["matchdays"]
    _assert(len(matchdays) == 10 and [md["md"] for md in matchdays] == list(range(1, 11)), "expected matchdays 1–10")
    for md in matchdays:
        _assert(len(md["results"]) == 6, f"matchday {md['md']} must contain six fixtures")
        _assert(len({team for game in md["results"] for team in (game["home"], game["away"])}) == 12,
                f"a team is missing or duplicated on matchday {md['md']}")
    computed = _league_table(matchdays)
    _assert(computed == history["table"], "stored league table does not recompute from matchday results")
    table = {row["team_id"]: row for row in computed}
    for team, position, wins, draws, losses, points in (
        ("RED", 4, 6, 1, 3, 19), ("WHI", 2, 7, 2, 1, 23),
    ):
        row = table[team]
        _assert((row["position"], row["w"], row["d"], row["l"], row["pts"]) ==
                (position, wins, draws, losses, points), f"{team} table facts do not match §5.2")
        _assert(row["p"] == 10, f"{team} did not play ten matches")
    _assert(all(row["p"] == 10 for row in computed), "every league team must play ten matches")

    lines = history["player_lines"]
    player_lines: dict[str, list[dict]] = defaultdict(list)
    for line in lines:
        _assert(line["team_id"] in {"RED", "WHI"}, "full player lines may only cover RED and WHI")
        _assert(line["player_id"].startswith(line["team_id"] + "-"), "player-line team and id disagree")
        player_lines[line["player_id"]].append(line)
        _assert(line["passes_completed"] <= line["passes"], f"invalid completed passes for {line['player_id']}")
    for team, roster in squads.items():
        _assert(len(roster) == 18, f"{team} must have 18 players")
    for player_id, lines_for_player in player_lines.items():
        _assert(player_id in {p["id"] for roster in squads.values() for p in roster}, f"unknown player line {player_id}")
    for player_id, player in dossiers["players"].items():
        player_rows = sorted(player_lines[player_id], key=lambda row: row["md"])
        expected = {
            "apps": len(player_rows), "starts": sum(row["started"] for row in player_rows),
            "minutes": sum(row["minutes"] for row in player_rows),
            "top_speed_kmh": round(max((row["top_speed_kmh"] for row in player_rows), default=0), 1),
            "pass_accuracy": round(100 * sum(row["passes_completed"] for row in player_rows) /
                                    sum(row["passes"] for row in player_rows), 1) if sum(row["passes"] for row in player_rows) else 0.0,
            "last5_ratings": [row["rating"] for row in player_rows[-5:]],
        }
        for field in LINE_SUM_FIELDS:
            expected[field] = sum(row[field] for row in player_rows)
        for field, value in expected.items():
            _assert(player.get(field) == value, f"dossier aggregate mismatch: {player_id}.{field}: {player.get(field)} != {value}")
        minutes = expected["minutes"]
        per90_metrics = ("goals", "assists", "shots", "key_passes", "dribbles_won", "tackles",
                         "progressive_passes", "aerials_won")
        for metric in per90_metrics:
            numerator = sum(row[metric] for row in player_rows)
            value = round(90 * numerator / minutes, 3) if minutes else 0.0
            _assert(player["per90"][metric] == value, f"per-90 aggregate mismatch: {player_id}.{metric}")

    rows = {row["metric"]: row["leaders"] for row in history["player_lines_league_leaders"]}
    _assert({"aerials_won", "dribbles_won_per90", "key_passes_per90", "progressive_passes"}.issubset(rows),
            "league-leader summary is missing a pinned metric")
    for metric in rows:
        _assert(rows[metric] == sorted(rows[metric], key=lambda row: (-row["value"], row["player_id"])),
                f"league leaders for {metric} are not ranked")
    _assert(dossiers["players"]["RED-9"]["goals"] == 7, "Falk must have seven league goals")
    red_homes = [line for line in player_lines["RED-9"] if line["home"]]
    _assert(len(red_homes) >= 3 and all(line["goals"] > 0 for line in sorted(red_homes, key=lambda x: x["md"])[-3:]),
            "Falk must score in Redmoor's latest three home matches")
    _assert(dossiers["players"]["RED-9"]["league_ranks"]["aerials_won"] == 1, "Falk must lead aerials")
    moretti = dossiers["players"]["RED-7"]
    _assert(moretti["league_ranks"]["dribbles_won_per90"] == 1, "Moretti must lead successful dribbles per 90")
    _assert(moretti["top_speed_kmh"] == 34.2, "Moretti season top speed must be 34.2 km/h")
    lindqvist = dossiers["players"]["RED-19"]
    _assert(lindqvist["age"] == 19 and lindqvist["apps"] == 3 and lindqvist["starts"] == 0 and lindqvist["goals"] == 0,
            "Lindqvist pinned league profile is incorrect")
    _assert(dossiers["players"]["RED-1"]["penalties_faced"] == 3 and
            dossiers["players"]["RED-1"]["penalties_saved"] == 2, "Wrona penalty record is incorrect")
    _assert(dossiers["players"]["RED-4"]["yellow"] == 3, "Duarte must have three league yellows")
    _assert(dossiers["players"]["WHI-3"]["yellow"] == 2, "Whitaker must have two league yellows")
    novak = dossiers["players"]["WHI-10"]
    _assert(novak["league_ranks"]["key_passes_per90"] == 1 and novak["league_ranks"]["progressive_passes"] == 1,
            "Novak must lead key passes per 90 and progressive passes")
    ferreira = dossiers["players"]["WHI-11"]
    _assert(ferreira["goals"] == 4 and ferreira["sub_goals"] == 3, "Ferreira scoring splits are incorrect")
    ferreira_lines = player_lines["WHI-11"]
    _assert(sum(not line["started"] for line in ferreira_lines) == 3 and sum(line["started"] for line in ferreira_lines) == 1,
            "Ferreira must have three substitute and one starting appearance")
    h2h = history["head_to_head"]
    _assert(len(h2h) == 3, "expected three previous head-to-head matches")
    h2h_whi_wins = sum((row["home"] == "WHI" and row["home_goals"] > row["away_goals"]) or
                       (row["away"] == "WHI" and row["away_goals"] > row["home_goals"]) for row in h2h)
    h2h_draws = sum(row["home_goals"] == row["away_goals"] for row in h2h)
    _assert((h2h_whi_wins, h2h_draws) == (2, 1), "H2H must be two Whitcliffe wins and one draw")
    whi_results = []
    for md in matchdays:
        game = next(row for row in md["results"] if "WHI" in (row["home"], row["away"]))
        gf, ga = ((game["home_goals"], game["away_goals"]) if game["home"] == "WHI" else
                  (game["away_goals"], game["home_goals"]))
        whi_results.append("W" if gf > ga else "D" if gf == ga else "L")
    _assert("L" not in whi_results[-6:], "Whitcliffe must be unbeaten in the last six")


def _validate_events(squads: dict, data: dict) -> tuple[dict, dict, float, float]:
    meta, events = data["meta"], data["events"]
    _assert(1600 <= len(events) <= 2400, f"event volume outside 1,600–2,400: {len(events)}")
    _assert([event["id"] for event in events] == list(range(1, len(events) + 1)), "event ids must be sequential")
    _assert(all(events[index]["t"] <= events[index + 1]["t"] for index in range(len(events) - 1)), "events are not sorted")
    _assert(len({event["id"] for event in events}) == len(events), "event ids are not unique")
    all_players = {player["id"]: player for roster in squads.values() for player in roster}
    active = {team: list(meta["lineups"][team]) for team in ("RED", "WHI")}
    _assert(len(active["RED"]) == 11 and len(active["WHI"]) == 11, "lineups must start 11 v 11")
    pitch_speed_peak: dict[str, float] = defaultdict(float)
    prev_positions: dict[str, tuple[float, float]] = {}
    prev_t = None
    max_speed = 0.0
    type_counts = Counter()
    passes = Counter()
    pass_complete = Counter()
    shots = Counter()
    shot_speeds = []
    score = {"RED": 0, "WHI": 0}
    goal_stack = {"RED": [], "WHI": []}
    snapshots = {}
    red_card_t = None
    substitutions = set()
    card_records = []
    for event in events:
        _assert(set(event) == EVENT_KEYS, f"event {event['id']} does not match §5.6 field names")
        _assert(event["type"] in EVENT_TYPES, f"unknown event type {event['type']}")
        type_counts[event["type"]] += 1
        _assert(event["team_id"] in {None, "RED", "WHI"}, f"invalid team at event {event['id']}")
        for key in ("start", "end"):
            point = event[key]
            if point is not None:
                _assert(0 <= point["x"] <= PITCH_X and 0 <= point["y"] <= PITCH_Y,
                        f"event {event['id']} {key} is out of bounds")
        player_id = event["player_id"]
        team = event["team_id"]
        if player_id is not None:
            _assert(player_id in all_players and all_players[player_id]["team_id"] == team,
                    f"unknown or mismatched event player at {event['id']}")
        is_sub = event["type"] == "substitution"
        if is_sub:
            incoming, outgoing = event["player_id"], event["related_player_id"]
            _assert(incoming not in active[team] and outgoing in active[team], f"invalid substitution at {event['id']}")
            active[team][active[team].index(outgoing)] = incoming
            substitutions.add((incoming, outgoing))
        elif player_id is not None:
            _assert(player_id in active[team], f"off-pitch player {player_id} appears at event {event['id']}")
        if event["related_player_id"] is not None:
            related = event["related_player_id"]
            _assert(related in all_players, f"unknown related player at {event['id']}")
            if not is_sub:
                _assert(related in active[all_players[related]["team_id"]],
                        f"off-pitch related player {related} appears at event {event['id']}")
        frame = event["frame"]
        _assert(set(frame) == {"ball", "players"}, f"frame shape mismatch at event {event['id']}")
        expected_ids = active["RED"] + active["WHI"]
        frame_ids = [row["id"] for row in frame["players"]]
        _assert(len(frame_ids) == len(expected_ids) and set(frame_ids) == set(expected_ids),
                f"frame on-pitch player list mismatch at event {event['id']}: {len(frame_ids)}")
        for point in [frame["ball"], *frame["players"]]:
            _assert(0 <= point["x"] <= PITCH_X and 0 <= point["y"] <= PITCH_Y,
                    f"frame coordinate out of bounds at event {event['id']}")
        if prev_t is not None:
            dt = event["t"] - prev_t
            _assert(dt > 0, "event timestamps must be strictly increasing")
            before = prev_positions
            current = {row["id"]: (row["x"], row["y"]) for row in frame["players"]}
            for pid in set(before) & set(current):
                distance = math.dist(before[pid], current[pid])
                allowed = max(MAX_SPEED_MPS * dt, 1.0) + 0.16
                _assert(distance <= allowed, f"player {pid} moved {distance:.2f}m in {dt:.2f}s at event {event['id']}")
                if dt >= 0.8:
                    speed = distance / dt * 3.6
                    pitch_speed_peak[pid] = max(pitch_speed_peak[pid], speed)
                    max_speed = max(max_speed, speed)
            prev_positions = current
        else:
            prev_positions = {row["id"]: (row["x"], row["y"]) for row in frame["players"]}
        prev_t = event["t"]

        if event["type"] == "pass":
            passes[team] += 1
            if event["outcome"] == "complete":
                pass_complete[team] += 1
        if event["type"] == "shot":
            shots[team] += 1
            shot_speeds.append(event["ball_speed_kmh"])
        if event["type"] == "penalty_taken":
            shot_speeds.append(event["ball_speed_kmh"])
        if event["type"] == "goal":
            score[team] += 1
            goal_stack[team].append(event)
            if (event["player_id"], event["minute"]) == ("RED-9", 18):
                snapshots["18"] = tuple(score[k] for k in ("RED", "WHI"))
            if (event["player_id"], event["minute"]) == ("WHI-9", 38):
                snapshots["38"] = tuple(score[k] for k in ("RED", "WHI"))
            if (event["player_id"], event["minute"]) == ("WHI-11", 67):
                snapshots["67"] = tuple(score[k] for k in ("RED", "WHI"))
            if (event["player_id"], event["minute"]) == ("RED-19", 88):
                snapshots["88"] = tuple(score[k] for k in ("RED", "WHI"))
            if (event["player_id"], event["added"]) == ("RED-7", 3):
                snapshots["90+3"] = tuple(score[k] for k in ("RED", "WHI"))
        if event["type"] == "var_decision":
            _assert(event["var"] == {"check": "offside", "decision": "goal_disallowed"}, "VAR decision payload mismatch")
            _assert(goal_stack["RED"], "VAR disallowed no preceding Redmoor goal")
            goal_stack["RED"].pop()
            score["RED"] -= 1
            snapshots["var"] = tuple(score[k] for k in ("RED", "WHI"))
        if event["type"] == "card":
            card_records.append((event["minute"], event["card"], event["player_id"]))
            if event["card"] == "second_yellow":
                red_card_t = event["t"]
        if event["type"] == "full_time":
            _assert(tuple(score[k] for k in ("RED", "WHI")) == (3, 2), "event score at full time is not 3-2")
        if event["type"] == "card" and event["card"] == "second_yellow":
            active[team].remove(player_id)

    _assert(snapshots.get("18") == (1, 0), f"18' score should be 1-0; got {snapshots.get('18')}")
    # The spec's phrase “back to 0-0” conflicts with its 18' scored goal and 38' 1-1 chain.
    # Interpret the 27' VAR as canceling its own provisional second goal, retaining the 18' goal.
    _assert(snapshots.get("var") == (1, 0), f"post-VAR score should retain the 18' goal; got {snapshots.get('var')}")
    _assert(snapshots.get("38") == (1, 1), f"38' score should be 1-1; got {snapshots.get('38')}")
    _assert(snapshots.get("67") == (1, 2), f"67' score should be 1-2; got {snapshots.get('67')}")
    _assert(snapshots.get("88") == (2, 2), f"88' score should be 2-2; got {snapshots.get('88')}")
    _assert(snapshots.get("90+3") == (3, 2), f"90+3' score should be 3-2; got {snapshots.get('90+3')}")
    _assert(meta["final_score"] == [3, 2], "match meta final score must be 3-2")
    _assert(meta["period_start_t"]["2"] == meta["half_time_t"] + 1.0, "second-half kickoff must follow half-time by one second")
    _assert(meta["full_time_t"] == events[-1]["t"], "full-time metadata must match final event")

    # Script anchors and participants.
    by_type = defaultdict(list)
    for event in events:
        by_type[event["type"]].append(event)
    find = lambda kind, predicate: next((e for e in by_type[kind] if predicate(e)), None)
    _assert(find("card", lambda e: e["minute"] == 9 and e["player_id"] == "WHI-3" and e["card"] == "yellow") is not None,
            "9' Whitaker yellow is missing")
    _assert(find("goal", lambda e: e["minute"] == 18 and e["player_id"] == "RED-9" and e["related_player_id"] == "RED-2") is not None,
            "18' Falk header from Reid is missing")
    var_check = find("var_check", lambda e: e["minute"] == 27)
    var_decision = find("var_decision", lambda e: e["minute"] == 27)
    _assert(var_check is not None and var_decision is not None, "27' VAR review events are missing")
    _assert(find("injury", lambda e: e["minute"] == 33 and e["player_id"] == "WHI-5") is not None,
            "33' Vuković injury is missing")
    berg_sub = find("substitution", lambda e: e["player_id"] == "WHI-4" and e["related_player_id"] == "WHI-5")
    _assert(berg_sub is not None and berg_sub["minute"] == 33, "Berg-for-Vuković sub is missing")
    pass_38 = find("pass", lambda e: e["player_id"] == "WHI-10" and e["subtype"] == "through_ball" and e["minute"] == 38)
    _assert(pass_38 is not None and pass_38["outcome"] == "complete" and pass_38["under_pressure"], "Novak high-difficulty pass is missing")
    distance = math.dist((pass_38["start"]["x"], pass_38["start"]["y"]), (pass_38["end"]["x"], pass_38["end"]["y"]))
    _assert(25 <= distance <= 35 and pass_38["end"]["x"] < pass_38["start"]["x"] and pass_38["end"]["x"] <= 16.5,
            f"38' through ball must travel 25–35m forward into Whitcliffe's box; got {distance:.1f}m")
    bypassed = sum(min(pass_38["start"]["x"], pass_38["end"]["x"]) <= row["x"] <=
                   max(pass_38["start"]["x"], pass_38["end"]["x"])
                   for row in pass_38["frame"]["players"] if row["id"].startswith("RED-"))
    _assert(bypassed >= 2, "38' through ball must bypass several opponents")
    _assert(find("goal", lambda e: e["minute"] == 38 and e["player_id"] == "WHI-9" and e["related_player_id"] == "WHI-10") is not None,
            "38' Visser goal/Novak assist is missing")
    _assert(find("card", lambda e: e["minute"] == 52 and e["player_id"] == "RED-4" and e["card"] == "yellow") is not None,
            "52' Duarte yellow is missing")
    _assert(find("penalty_awarded", lambda e: e["team_id"] == "WHI") is not None, "Whitcliffe penalty award missing")
    _assert(find("penalty_taken", lambda e: e["player_id"] == "WHI-9" and e["outcome"] == "saved") is not None,
            "Visser's saved penalty is missing")
    _assert(find("save", lambda e: e["player_id"] == "RED-1" and e["related_player_id"] == "WHI-9") is not None,
            "Wrona penalty save event is missing")
    _assert(find("card", lambda e: e["minute"] == 61 and e["player_id"] == "RED-4" and e["card"] == "second_yellow") is not None,
            "61' Duarte dismissal is missing")
    expected_subs = {("RED-15", "RED-14"), ("RED-16", "RED-8"), ("WHI-11", "WHI-17"),
                     ("WHI-14", "WHI-18"), ("WHI-16", "WHI-7"), ("RED-19", "RED-11"), ("RED-17", "RED-9")}
    _assert(expected_subs.issubset(substitutions), f"missing scripted substitutions: {expected_subs - substitutions}")
    _assert(find("goal", lambda e: e["minute"] == 67 and e["player_id"] == "WHI-11" and e["related_player_id"] == "WHI-10") is not None,
            "67' Ferreira goal/Novak assist missing")
    _assert(find("shot", lambda e: e["minute"] == 81 and e["player_id"] == "WHI-10" and e["outcome"] == "post") is not None,
            "81' Novak post is missing")
    _assert(find("clearance", lambda e: e["minute"] == 84 and e["player_id"] == "RED-5" and e["subtype"] == "goal_line") is not None,
            "84' Dahl goal-line clearance is missing")
    _assert(find("goal", lambda e: e["minute"] == 88 and e["player_id"] == "RED-19" and e["related_player_id"] == "RED-3") is not None,
            "88' Lindqvist goal from Laurent cross missing")
    _assert(find("dribble", lambda e: e["player_id"] == "RED-7" and e["related_player_id"] == "WHI-3" and
                 e["outcome"] == "won" and e["t"] >= 5700) is not None, "90'+3 Moretti winner duel missing")
    early_duels = [e for e in by_type["dribble"] if e["player_id"] == "RED-7" and e["related_player_id"] == "WHI-3"
                   and e["outcome"] == "won" and e["t"] <= 900]
    _assert(len(early_duels) >= 4, "Moretti must beat Whitaker at least four times by 15'")
    _assert(type_counts["half_time"] == 1 and type_counts["full_time"] == 1, "half/full-time events missing")
    _assert(red_card_t is not None and all(len(event["frame"]["players"]) == 21 for event in events if event["t"] > red_card_t),
            "every frame after the dismissal must contain 21 players")
    _assert(all(len(event["frame"]["players"]) == 22 for event in events if event["t"] < red_card_t),
            "frames before the dismissal must contain 22 players")

    for team in ("RED", "WHI"):
        _assert(450 <= passes[team] <= 600, f"{team} pass count outside 450–600: {passes[team]}")
        accuracy = pass_complete[team] / passes[team] * 100
        _assert(78 <= accuracy <= 89, f"{team} pass accuracy outside 78–89%: {accuracy:.1f}%")
        _assert(10 <= shots[team] <= 18, f"{team} shot count outside 10–18: {shots[team]}")
    _assert(shot_speeds and all(60 <= speed <= 120 for speed in shot_speeds), "shot speed outside 60–120 km/h")
    moretti_peak = pitch_speed_peak["RED-7"]
    _assert(33.5 <= moretti_peak <= 35.0, f"Moretti frame-derived peak speed should be about 34.5 km/h, got {moretti_peak:.1f}")
    _assert(max_speed <= 35.5, f"frame-derived sprint exceeded 35.5 km/h: {max_speed:.1f}")
    _assert(0 <= meta["period_start_t"]["2"] < meta["half_time_t"] + 2, "invalid period start metadata")

    # Event-time possession and match phases follow the expected control shifts.
    possession = {"RED": 0.0, "WHI": 0.0}
    owner, previous_t = "RED", 0.0
    early_counts = Counter()
    press_counts = Counter()
    for event in events:
        if event["t"] > meta["half_time_t"]:
            break
        possession[owner] += event["t"] - previous_t
        previous_t = event["t"]
        if event["team_id"] in possession:
            owner = event["team_id"]
        if event["t"] <= 900 and event["team_id"] in possession:
            early_counts[event["team_id"]] += 1
        if 1500 <= event["t"] <= 2220 and event["team_id"] in possession:
            press_counts[event["team_id"]] += 1
    red_possession = possession["RED"] / sum(possession.values()) * 100
    _assert(52 <= red_possession <= 58, f"first-half RED possession should be roughly 55%, got {red_possession:.1f}%")
    _assert(early_counts["RED"] >= early_counts["WHI"] * 1.5, "Redmoor should dominate the opening 15 minutes")
    _assert(press_counts["WHI"] > press_counts["RED"], "Whitcliffe's 25'–37' press should shift control")
    chaos = [event for event in events if 4680 <= event["t"] <= 5160]
    chaos_sides = {event["team_id"] for event in chaos if event["type"] == "shot"}
    _assert({"RED", "WHI"}.issubset(chaos_sides), "78'–86' chaos phase needs shots from both teams")

    # Scripted stoppages provide the quiet windows consumed by the commentary scheduler.
    for scorer in [e for e in by_type["goal"] if e["player_id"] in {"RED-9", "WHI-9", "WHI-11", "RED-19", "RED-7"}]:
        overturned = any(e["type"] == "var_decision" and scorer["t"] < e["t"] < scorer["t"] + 75 for e in events)
        if not overturned:
            restart = next(e for e in events if e["type"] == "kickoff" and e["t"] > scorer["t"])
            _assert(restart["t"] - scorer["t"] >= 39.9, "goal celebration quiet window must be about 40 seconds")
    injury = next(e for e in by_type["injury"] if e["player_id"] == "WHI-5")
    injury_sub = next(e for e in by_type["substitution"] if e["player_id"] == "WHI-4")
    _assert(44 <= injury_sub["t"] - injury["t"] <= 60, "injury stoppage should last 40–60 seconds")
    var_restart = next(e for e in by_type["goal_kick"] if e["t"] > var_check["t"])
    _assert(59 <= var_restart["t"] - var_check["t"] <= 61, "VAR review quiet window should be about 60 seconds")
    for minute in (9, 61):
        card = next(e for e in by_type["card"] if e["minute"] == minute)
        restart = next(e for e in events if e["t"] > card["t"] and e["restart"] == "free_kick")
        _assert(restart["t"] - card["t"] >= 19.9, f"{minute}' card quiet window should be about 20 seconds")
    return {"RED": passes["RED"], "WHI": passes["WHI"]}, {
        "RED": pass_complete["RED"] / passes["RED"] * 100,
        "WHI": pass_complete["WHI"] / passes["WHI"] * 100,
    }, max(shots.values()), moretti_peak, red_possession


def validate() -> None:
    teams = _load("teams.json")["teams"]
    squads = _load("squads.json")
    history = _load("league_history.json")
    dossiers = _load("dossiers.json")
    match = _load("match_events.json")
    _assert(len(teams) == 12, "expected two match teams plus ten league teams")
    team_by_id = {team["id"]: team for team in teams}
    _assert(team_by_id["RED"]["color_primary"] == "#d7263d" and team_by_id["RED"]["color_secondary"] == "#ffffff",
            "Redmoor colors are incorrect")
    _assert(team_by_id["WHI"]["color_primary"] == "#f2f2f2" and team_by_id["WHI"]["color_secondary"] == "#111111",
            "Whitcliffe colors are incorrect")
    _validate_history(squads, history, dossiers)
    passes, accuracy, max_shots, moretti_peak, red_possession = _validate_events(squads, match)
    sizes = {path.name: path.stat().st_size for path in sorted(DATA_DIR.glob("*.json"))}
    _assert(sizes["match_events.json"] < 6_000_000, f"match_events.json is too large: {sizes['match_events.json']} bytes")
    print("Spotter synthetic data realism report")
    print("+------------------+----------+----------+----------+")
    print("| Metric           | RED      | WHI      | Match    |")
    print("+------------------+----------+----------+----------+")
    print(f"| Passes           | {passes['RED']:>8} | {passes['WHI']:>8} |          |")
    print(f"| Pass accuracy    | {accuracy['RED']:>7.1f}% | {accuracy['WHI']:>7.1f}% |          |")
    print(f"| Shots            | {sum(e['team_id']=='RED' and e['type']=='shot' for e in match['events']):>8} | "
          f"{sum(e['team_id']=='WHI' and e['type']=='shot' for e in match['events']):>8} |          |")
    print(f"| Events / peak km/h|          |          | {len(match['events']):>4} / {moretti_peak:.1f} |")
    print("+------------------+----------+----------+----------+")
    print(f"First-half possession: RED {red_possession:.1f}% / WHI {100-red_possession:.1f}%; opening control and press-phase shift validated.")
    print("Table: WHI 2nd (23 pts), RED 4th (19 pts); H2H WHI 2W-1D; WHI unbeaten in last 6.")
    print(f"Generated JSON sizes: {', '.join(f'{name}={size:,}B' for name, size in sizes.items())}")


if __name__ == "__main__":
    validate()
