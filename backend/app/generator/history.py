"""Seeded league history and dossiers derived from player match lines."""

from __future__ import annotations

import random
from collections import defaultdict

from .squads import TEAM_DATA, build_squads

TEAM_IDS = [team["id"] for team in TEAM_DATA]
TARGET_FORM = {
    # W/D/L by matchday; the RED and WHI totals are pinned by §5.2.
    "RED": ["W", "L", "W", "W", "L", "W", "D", "L", "W", "W"],
    "WHI": ["W", "W", "L", "D", "W", "W", "W", "W", "D", "W"],
}


def _fixtures(seed: int = 42) -> list[list[tuple[str, str]]]:
    rng = random.Random(seed + 7)
    order = TEAM_IDS[:]
    # Find a deterministic rotation with RED-WHI included in the ten played rounds.
    for _ in range(100):
        rng.shuffle(order)
        ring = order[:]
        rounds = []
        for day in range(11):
            pairs = []
            for i in range(6):
                a, b = ring[i], ring[11 - i]
                home, away = (a, b) if (day + i) % 2 == 0 else (b, a)
                pairs.append((home, away))
            rounds.append(pairs)
            ring = [ring[0], ring[-1], *ring[1:-1]]
        # Re-orient each fixture greedily so every club has a realistic five home games.
        home_counts = {team: 0 for team in TEAM_IDS}
        first_ten = []
        for day, fixtures in enumerate(rounds[:10]):
            oriented = []
            for index, (a, b) in enumerate(fixtures):
                if home_counts[a] < home_counts[b]:
                    home, away = a, b
                elif home_counts[b] < home_counts[a]:
                    home, away = b, a
                else:
                    home, away = (a, b) if (day + index) % 2 == 0 else (b, a)
                home_counts[home] += 1
                oriented.append((home, away))
            first_ten.append(oriented)
        if any({a, b} == {"RED", "WHI"} for day in first_ten for a, b in day):
            return first_ten
    raise RuntimeError("unable to build matchday schedule")


def _table(results: list[dict]) -> list[dict]:
    rows = {team: {"team_id": team, "p": 0, "w": 0, "d": 0, "l": 0,
                   "gf": 0, "ga": 0, "gd": 0, "pts": 0} for team in TEAM_IDS}
    for result in results:
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
            home["d"] += 1; away["d"] += 1
            home["pts"] += 1; away["pts"] += 1
    for row in rows.values():
        row["gd"] = row["gf"] - row["ga"]
    ordered = sorted(rows.values(), key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["team_id"]))
    for position, row in enumerate(ordered, 1):
        row["position"] = position
    return ordered


def _result_for(home: str, away: str, day: int, rng: random.Random) -> tuple[int, int]:
    if home in TARGET_FORM:
        home_result = TARGET_FORM[home][day - 1]
    elif away in TARGET_FORM:
        away_result = TARGET_FORM[away][day - 1]
        home_result = {"W": "L", "D": "D", "L": "W"}[away_result]
    elif "ASH" in (home, away):
        home_result = "W" if home == "ASH" else "L"
    elif "BLK" in (home, away):
        home_result = "W" if home == "BLK" else "L"
    else:
        # Mid-table meetings are close, so neither can accumulate a fabricated runaway.
        home_result = "D"
    goals = {"W": (2 + (rng.random() < 0.28), 0 if rng.random() < 0.68 else 1),
             "D": (1 + (rng.random() < 0.35), 1 + (rng.random() < 0.35)),
             "L": (0 if rng.random() < 0.55 else 1, 2 + (rng.random() < 0.28))}
    hg, ag = goals[home_result]
    if home_result == "D":
        ag = hg
    return int(hg), int(ag)


def _player_lines(results_by_day: list[list[dict]], squads: dict[str, list[dict]], seed: int = 42) -> list[dict]:
    rng = random.Random(seed + 202)
    lines: list[dict] = []
    red_home_days = [day for day, games in enumerate(results_by_day, 1)
                     if any(g["home"] == "RED" for g in games)]
    red_home_days = red_home_days[-3:]
    red_goal_days = set(red_home_days)
    red_scoring_days = [day for day, games in enumerate(results_by_day, 1)
                        if any((g["home"] == "RED" and g["home_goals"] > 0) or
                               (g["away"] == "RED" and g["away_goals"] > 0) for g in games)]
    red_goal_days.update(red_scoring_days[:4])
    whi_scoring_days = [day for day, games in enumerate(results_by_day, 1)
                        if any((g["home"] == "WHI" and g["home_goals"] > 0) or
                               (g["away"] == "WHI" and g["away_goals"] > 0) for g in games)]
    ferreira_goal_days = whi_scoring_days[:4]
    ferreira_sub_days = set(ferreira_goal_days[:3])
    squads_by_id = {team: {p["id"]: p for p in group} for team, group in squads.items()}
    stat_lines: dict[tuple[str, int], dict[str, dict]] = {}

    for day, fixtures in enumerate(results_by_day, 1):
        for result in fixtures:
            for team, opponent, is_home, score, conceded in (
                (result["home"], result["away"], True, result["home_goals"], result["away_goals"]),
                (result["away"], result["home"], False, result["away_goals"], result["home_goals"]),
            ):
                if team not in squads:
                    continue
                team_lines = {}
                roster = squads[team]
                for player in roster:
                    pid = player["id"]
                    starter = player["starter"]
                    appears = starter or rng.random() < (0.44 if player["position"] != "GK" else 0.12)
                    if pid == "RED-19":
                        appears = day in {2, 5, 9}
                    if pid == "WHI-11":
                        appears = day in ferreira_sub_days or day == ferreira_goal_days[3]
                    if not appears:
                        continue
                    started = starter
                    if pid == "RED-19" or (pid == "WHI-11" and day in ferreira_sub_days):
                        started = False
                    if pid == "WHI-11" and day == ferreira_goal_days[3]:
                        started = True
                    minutes = rng.randint(68, 95) if started else rng.randint(12, 32)
                    if pid.endswith("-1"):
                        minutes = 90
                        started = True
                    stat = {
                        "md": day, "player_id": pid, "team_id": team, "opponent": opponent,
                        "home": is_home, "started": started, "minutes": minutes,
                        "goals": 0, "assists": 0, "shots": 0,
                        "passes": (65 if player["position"] in {"CM", "CDM", "CAM"} else 37) + rng.randint(0, 36),
                        "passes_completed": 0, "key_passes": rng.randint(0, 3),
                        "progressive_passes": rng.randint(2, 11),
                        "dribbles_attempted": rng.randint(0, 5), "dribbles_won": rng.randint(0, 4),
                        "tackles": rng.randint(0, 5), "aerials_won": rng.randint(0, 5),
                        "yellow": 0, "red": 0,
                        "top_speed_kmh": round(27.0 + rng.random() * 5.4, 1),
                        "rating": round(5.8 + rng.random() * 2.1, 1),
                        "penalties_faced": 0, "penalties_saved": 0, "sub_goals": 0,
                    }
                    accuracy = 0.79 + rng.random() * 0.095
                    stat["passes_completed"] = round(stat["passes"] * accuracy)
                    if not started and pid != "RED-7":
                        stat["dribbles_attempted"] = min(stat["dribbles_attempted"], 1)
                        stat["dribbles_won"] = min(stat["dribbles_won"], 1)
                    if pid == "RED-7":
                        stat["dribbles_attempted"] += 10
                        stat["dribbles_won"] += 9
                        stat["top_speed_kmh"] = 34.2 if day == 6 else min(33.8, stat["top_speed_kmh"])
                    if pid == "RED-9":
                        stat["aerials_won"] += 12
                    if pid == "WHI-10":
                        stat["key_passes"] += 13
                        stat["progressive_passes"] += 16
                    if pid == "RED-1" and day in {2, 6, 9}:
                        stat["penalties_faced"] = 1
                        stat["penalties_saved"] = 1 if day in {2, 9} else 0
                    if pid == "RED-4" and day in {2, 5, 8}:
                        stat["yellow"] = 1
                    if pid == "WHI-3" and day in {3, 7}:
                        stat["yellow"] = 1
                    if pid == "RED-19":
                        stat["rating"] = round(6.2 + rng.random() * 0.8, 1)
                    team_lines[pid] = stat
                stat_lines[(team, day)] = team_lines

    # Assign goal scorers to actual goals in results while reserving the scripted league facts.
    for team, target, days in (("RED", "RED-9", sorted(red_goal_days)[:7]),
                               ("WHI", "WHI-11", ferreira_goal_days)):
        for day in days:
            line = stat_lines.get((team, day), {}).get(target)
            if line:
                line["goals"] += 1
                line["shots"] += 1
                if team == "WHI" and day in ferreira_sub_days:
                    line["sub_goals"] += 1
    # Complete remaining team goals, keeping score totals coherent.
    for day, fixtures in enumerate(results_by_day, 1):
        for result in fixtures:
            for team, goals in ((result["home"], result["home_goals"]), (result["away"], result["away_goals"])):
                if team not in squads:
                    continue
                rows = stat_lines.get((team, day), {})
                current = sum(line["goals"] for line in rows.values())
                scorers = [pid for pid in rows if pid not in {"RED-9", "WHI-11"}]
                for n in range(max(0, goals - current)):
                    if scorers:
                        scorer = scorers[(day + n) % len(scorers)]
                        rows[scorer]["goals"] += 1
                        rows[scorer]["shots"] += 1
                for row in rows.values():
                    row["assists"] = 1 if goals and row["goals"] == 0 and row["key_passes"] > 1 and rng.random() < 0.13 else 0
                lines.extend(rows.values())

    # Enforce exact pinned counts against the generated match lines.
    for pid, field, value in (("RED-9", "goals", 7), ("RED-4", "yellow", 3), ("WHI-3", "yellow", 2),
                              ("WHI-11", "goals", 4), ("WHI-11", "sub_goals", 3)):
        selected = [line for line in lines if line["player_id"] == pid]
        for line in selected:
            line[field] = 0
        if pid == "RED-9":
            selected.sort(key=lambda line: (line["md"] not in red_home_days, line["md"]))
        elif pid == "WHI-11":
            selected.sort(key=lambda line: (line["md"] not in ferreira_goal_days, line["md"]))
        else:
            selected.sort(key=lambda line: line["md"])
        for line in selected[:value]:
            line[field] = 1
            if field == "goals":
                line["shots"] = max(line["shots"], 1)
        if pid == "WHI-11":
            sub_lines = [line for line in selected if not line["started"]]
            for line in sub_lines[:3]:
                line["sub_goals"] = 1
    return sorted(lines, key=lambda line: (line["md"], line["team_id"], line["player_id"]))


def build_history(seed: int = 42) -> tuple[dict, dict, dict]:
    rng = random.Random(seed + 41)
    schedule = _fixtures(seed)
    matchdays = []
    results_by_day = []
    for md, fixtures in enumerate(schedule, 1):
        results = []
        for home, away in fixtures:
            hg, ag = _result_for(home, away, md, rng)
            results.append({"home": home, "away": away, "home_goals": hg, "away_goals": ag})
        matchdays.append({"md": md, "results": results})
        results_by_day.append(results)

    # Ensure Falk scored in each of Redmoor's three latest home games and scores are nonzero.
    red_home_md = [md for md, fixtures in enumerate(results_by_day, 1) if any(f["home"] == "RED" for f in fixtures)][-3:]
    for md in red_home_md:
        for game in results_by_day[md - 1]:
            if game["home"] == "RED" and game["home_goals"] == 0:
                game["home_goals"] = 1
    # Reconcile target win/draw/loss results after the score guarantee.
    # The result assignments already give RED six wins, a draw and three losses;
    # latest-home score adjustment only changes 0-1 to 1-1 where necessary.
    flat_results = [game for games in results_by_day for game in games]
    table = _table(flat_results)
    squads = build_squads()
    player_lines = _player_lines(results_by_day, squads, seed)
    # Recompute table after any home-score adjustment (rather than storing a typed aggregate).
    table = _table(flat_results)

    leaders = _league_leaders(player_lines, squads)
    head_to_head = [
        {"season": season, "home": home, "away": away, "home_goals": hg, "away_goals": ag}
        for season, home, away, hg, ag in (
            ("2025/26", "WHI", "RED", 2, 1),
            ("2024/25", "RED", "WHI", 0, 0),
            ("2024/25", "WHI", "RED", 1, 0),
        )
    ]
    history = {"matchdays": matchdays, "player_lines": player_lines,
               "player_lines_league_leaders": leaders,
               "head_to_head": head_to_head, "table": table}
    dossiers = build_dossiers(history, squads)
    return history, dossiers, squads


def _league_leaders(lines: list[dict], squads: dict) -> list[dict]:
    players = {p["id"]: p for group in squads.values() for p in group}
    totals: dict[str, dict] = defaultdict(lambda: {"minutes": 0, "goals": 0, "dribbles_won": 0,
                                                    "aerials_won": 0, "key_passes": 0,
                                                    "progressive_passes": 0})
    for line in lines:
        row = totals[line["player_id"]]
        row["minutes"] += line["minutes"]
        for metric in ("goals", "dribbles_won", "aerials_won", "key_passes", "progressive_passes"):
            row[metric] += line[metric]
    # Synthetic league leaders let dossiers verify league-best claims without invented squad names.
    external = {
        "goals_per90": ("ASH-9", "ASH", 17, 1_350),
        "dribbles_won_per90": ("LAR-7", "LAR", 42, 1_300),
        "aerials_won": ("BLK-5", "BLK", 71, 1_500),
        "key_passes_per90": ("ASH-10", "ASH", 88, 1_440),
        "progressive_passes": ("BLK-8", "BLK", 99, 1_500),
    }
    metrics = {
        "goals_per90": lambda p, v: 90 * v["goals"] / max(1, v["minutes"]),
        "dribbles_won_per90": lambda p, v: 90 * v["dribbles_won"] / max(1, v["minutes"]),
        "aerials_won": lambda p, v: v["aerials_won"],
        "key_passes_per90": lambda p, v: 90 * v["key_passes"] / max(1, v["minutes"]),
        "progressive_passes": lambda p, v: v["progressive_passes"],
    }
    output = []
    for metric, calculate in metrics.items():
        candidates = []
        for pid, totals_row in totals.items():
            value = calculate(pid, totals_row)
            candidates.append({"player_id": pid, "team_id": players[pid]["team_id"],
                               "name": players[pid]["name"], "value": round(value, 3),
                               "minutes": totals_row["minutes"]})
        ext = external[metric]
        candidates.append({"player_id": ext[0], "team_id": ext[1], "name": f"{ext[1]} league player",
                           "value": round(ext[2] * (90 / ext[3]) if metric.endswith("per90") else ext[2], 3),
                           "minutes": ext[3]})
        if metric == "goals_per90":
            candidates = [row for row in candidates if row["player_id"] != "ASH-9"]
        candidates.sort(key=lambda row: (-row["value"], row["player_id"]))
        output.append({"metric": metric, "leaders": candidates[:10]})
    return output


def build_dossiers(history: dict, squads: dict) -> dict:
    players = {p["id"]: p for team in squads.values() for p in team}
    by_player: dict[str, list[dict]] = defaultdict(list)
    for line in history["player_lines"]:
        by_player[line["player_id"]].append(line)
    leaders = {row["metric"]: row["leaders"] for row in history["player_lines_league_leaders"]}
    metrics = ("goals", "assists", "shots", "key_passes", "dribbles_won", "tackles", "yellow", "red",
               "passes", "passes_completed", "progressive_passes", "aerials_won", "minutes")
    dossiers = {}
    for pid, player in players.items():
        lines = sorted(by_player.get(pid, []), key=lambda row: row["md"])
        sums = {metric: sum(line[metric] for line in lines) for metric in metrics}
        sums["penalties_faced"] = sum(line["penalties_faced"] for line in lines)
        sums["penalties_saved"] = sum(line["penalties_saved"] for line in lines)
        sums["sub_goals"] = sum(line["sub_goals"] for line in lines)
        minutes = sums["minutes"]
        per90 = {metric: round(90 * sums[metric] / minutes, 3) if minutes else 0.0
                 for metric in ("goals", "assists", "shots", "key_passes", "dribbles_won", "tackles",
                                "progressive_passes", "aerials_won")}
        ranks = {}
        for metric, rows in leaders.items():
            if metric == "goals_per90":
                value = per90["goals"]
            elif metric == "dribbles_won_per90":
                value = per90["dribbles_won"]
            elif metric == "key_passes_per90":
                value = per90["key_passes"]
            else:
                value = sums.get(metric, 0)
            ranked = sorted(rows, key=lambda row: (-row["value"], row["player_id"]))
            ranks[metric] = next((i for i, row in enumerate(ranked, 1) if row["player_id"] == pid),
                                 1 + sum(row["value"] > value for row in rows))
        pass_accuracy = round(100 * sums["passes_completed"] / sums["passes"], 1) if sums["passes"] else 0.0
        last5 = [line["rating"] for line in lines[-5:]]
        story_facts = []
        if sums["goals"]:
            story_facts.append(f"Has scored {sums['goals']} league goals in {len(lines)} appearances")
        if pid == "RED-9":
            homes = [line for line in lines if line["home"]]
            streak = 0
            for line in reversed(homes):
                if line["goals"]:
                    streak += 1
                else:
                    break
            story_facts = [f"Has scored in each of Redmoor's last {streak} home games"]
        elif pid == "RED-7":
            story_facts.append(f"Averages {per90['dribbles_won']:.2f} successful dribbles per 90")
        elif pid == "RED-19":
            story_facts = [f"Has made {len(lines)} substitute appearances without a league goal"]
        elif pid == "WHI-10":
            story_facts.append(f"Leads the league for key passes per 90 and has {sums['progressive_passes']} progressive passes")
        dossiers[pid] = {
            "number": player["number"], "position": player["position"], "age": player["age"],
            "nationality": player["nationality"], "height_cm": player["height_cm"], "foot": player["foot"],
            "apps": len(lines), "starts": sum(line["started"] for line in lines), "minutes": minutes,
            "goals": sums["goals"], "assists": sums["assists"], "shots": sums["shots"],
            "pass_accuracy": pass_accuracy, "key_passes": sums["key_passes"],
            "dribbles_won": sums["dribbles_won"], "tackles": sums["tackles"],
            "yellow": sums["yellow"], "red": sums["red"],
            "penalties_faced": sums["penalties_faced"], "penalties_saved": sums["penalties_saved"],
            "sub_goals": sums["sub_goals"],
            "top_speed_kmh": round(max((line["top_speed_kmh"] for line in lines), default=0), 1),
            "last5_ratings": last5, "per90": per90, "league_ranks": ranks,
            "story_facts": story_facts[:2],
        }
    table = {row["team_id"]: row for row in history["table"]}
    h2h = history["head_to_head"]
    teams = {}
    for team in ("RED", "WHI"):
        row = table[team]
        results = []
        for md in history["matchdays"]:
            game = next(g for g in md["results"] if team in {g["home"], g["away"]})
            gf = game["home_goals"] if game["home"] == team else game["away_goals"]
            ga = game["away_goals"] if game["home"] == team else game["home_goals"]
            results.append("W" if gf > ga else "D" if gf == ga else "L")
        unbeaten = 0
        for form in reversed(results):
            if form != "L": unbeaten += 1
            else: break
        team_h2h = [g for g in h2h if team in {g["home"], g["away"]}]
        wins = sum((g["home"] == team and g["home_goals"] > g["away_goals"]) or
                   (g["away"] == team and g["away_goals"] > g["home_goals"]) for g in team_h2h)
        draws = sum(g["home_goals"] == g["away_goals"] for g in team_h2h)
        fact = f"Unbeaten in the last {unbeaten} league matches" if team == "WHI" else f"Won {row['w']} of {row['p']} league matches"
        teams[team] = {"position": row["position"], "p": row["p"], "w": row["w"], "d": row["d"],
                       "l": row["l"], "pts": row["pts"], "form_last5": results[-5:],
                       "unbeaten_run": unbeaten,
                       "h2h_summary": {"played": len(team_h2h), "wins": wins, "draws": draws,
                                       "losses": len(team_h2h) - wins - draws},
                       "story_facts": [fact, f"League position {row['position']} with {row['pts']} points"]}
    return {"players": dossiers, "teams": teams}
