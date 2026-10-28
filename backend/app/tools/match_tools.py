"""Function tools for proposer agents (spec §7.3). All read MatchState / StatsEngine / data files / the board.

Each builder returns Microsoft Agent Framework FunctionTools bound to a live Booth.
"""
from __future__ import annotations

import functools
import json
from typing import TYPE_CHECKING, Annotated, Any, Callable

from agent_framework import tool
from pydantic import Field

if TYPE_CHECKING:
    from ..booth import Booth

PlayerArg = Annotated[str, Field(description="Player id like 'RED-7' or 'WHI-10'")]
TeamArg = Annotated[str, Field(description="'RED' (Redmoor Rovers) or 'WHI' (Whitcliffe Athletic)")]
WindowArg = Annotated[str, Field(description="'match', '5min', '10min' or 'half'")]


def _j(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


def _safe(fn: Callable[..., Any]) -> Callable[..., str]:
    @functools.wraps(fn)
    def wrapper(*a: Any, **k: Any) -> str:
        try:
            return _j(fn(*a, **k))
        except Exception as e:  # noqa: BLE001 — tools must never crash the agent run
            return _j({"error": f"{type(e).__name__}: {e}"})
    return wrapper


def build_tools(booth: "Booth") -> dict[str, list[Any]]:
    st, data, board = booth.stats, booth.data, booth.board
    dossiers = data.dossiers

    def get_player_stats(player_id: PlayerArg, window: WindowArg = "match"):
        """This match's stats for one player in a time window (passes, pass difficulty, dribbles, shots, xG, speed, distance...)."""
        return st.player_stats(player_id, window)

    def get_team_stats(team: TeamArg, window: WindowArg = "match"):
        """This match's team stats in a window (possession, passes, accuracy, shots, xG, PPDA, territory...)."""
        return st.team_stats(team, window)

    def get_match_leaders(metric: Annotated[str, Field(description="A player_stats metric, e.g. 'dribbles_won', 'top_speed_kmh', 'avg_pass_difficulty', 'distance_km', 'key_passes'")]):
        """Top 5 players in this match for a metric."""
        return st.match_leaders(metric, 5)

    def get_alerts(since_t: Annotated[float, Field(description="Match seconds; use 0 for all alerts so far")] = 0.0):
        """Threshold alerts so far: top speeds, shot speeds, distance milestones, season bests, first goals, pass milestones."""
        return st.alerts_since(since_t)[-15:]

    def get_recent_cards():
        """Cards already on the booth board (newest first) with status. Do not repeat what was aired or is queued."""
        return board.recent(12)

    def get_control_chaos(window: Annotated[str, Field(description="'5min' or '10min'")] = "5min"):
        """Control index (per team, sums to 100) and chaos index (0-100), with a per-minute timeline."""
        return st.control_chaos(window)

    def compare_periods(a: Annotated[str, Field(description="Minute range 'MM-MM', e.g. '0-15'")],
                        b: Annotated[str, Field(description="Minute range 'MM-MM', e.g. '25-37'")]):
        """Compare team stats between two minute ranges of this match."""
        return st.compare_periods(a, b)

    def get_pressure(team: TeamArg, window: Annotated[str, Field(description="'5min' or '10min' or 'match'")] = "5min"):
        """Pressing metrics for a team: pressures, PPDA, turnovers forced, high regains."""
        return st.pressure(team, window)

    def get_average_shape(team: TeamArg, window: Annotated[str, Field(description="'5min' or '10min' or 'match'")] = "5min"):
        """Average positions, defensive line height, width and compactness for a team."""
        return st.average_shape(team, window)

    def get_player_matchup(a: PlayerArg, b: PlayerArg):
        """Head-to-head duels/dribbles/tackles between two players in this match."""
        return st.player_matchup(a, b)

    def get_win_probability():
        """Current win/draw/loss probability and the inputs used."""
        return st.win_probability()

    def get_player_dossier(player_id: PlayerArg):
        """Season dossier for a player (previous 10 matchdays): apps, goals, assists, per-90s, league ranks, form, story facts."""
        d = dossiers["players"].get(player_id)
        p = data.players.get(player_id, {})
        return {"name": p.get("name"), **(d or {"error": "unknown player"})}

    def get_team_dossier(team: TeamArg):
        """Season dossier for a team: league position, record, form, unbeaten run, story facts."""
        return dossiers["teams"].get(team, {"error": "unknown team"})

    def get_head_to_head():
        """Last meetings between Redmoor Rovers and Whitcliffe Athletic."""
        return data.history.get("head_to_head", [])

    def get_league_table():
        """League table before this matchday."""
        return data.history.get("table", [])

    def get_key_moments():
        """Key moments so far this match: goals, cards, VAR, penalties, subs, injuries, big chances."""
        return st.key_moments()

    def get_duels(a: PlayerArg, b: PlayerArg):
        """Duel history between two players this match (attempts, who won, event ids)."""
        return st.duels(a, b)

    def get_player_timeline(player_id: PlayerArg):
        """A player's key involvements so far this match."""
        return st.player_timeline(player_id)

    def get_aired_history():
        """Every card already aired this match, in order."""
        return [{"id": c.id, "agent": c.agent, "text": c.text, "t": c.created_t} for c in board.aired()]

    def get_squads():
        """Players on the pitch now and benches, with ids, names and positions."""
        on = booth.state.on_pitch
        return [{"id": p["id"], "name": p["name"], "pos": p["position"], "on_pitch": p["id"] in on}
                for p in data.players.values()]

    T = {name: tool(_safe(fn)) for name, fn in locals().items() if callable(fn) and name.startswith(("get_", "compare_"))}
    common = [T["get_recent_cards"], T["get_squads"]]
    return {
        "stats_scout": [T["get_player_stats"], T["get_team_stats"], T["get_match_leaders"], T["get_alerts"], *common],
        "tactical": [T["get_control_chaos"], T["compare_periods"], T["get_pressure"], T["get_average_shape"],
                     T["get_player_matchup"], T["get_win_probability"], T["get_team_stats"], *common],
        "dossier": [T["get_player_dossier"], T["get_team_dossier"], T["get_head_to_head"], T["get_league_table"],
                    T["get_player_stats"], *common],
        "storyline": [T["get_key_moments"], T["get_duels"], T["get_player_timeline"], T["get_aired_history"], *common],
    }
