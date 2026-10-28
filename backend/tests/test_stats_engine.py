import copy

from app.stats.engine import STATS_KEYS, StatsEngine
from app.stats.pass_difficulty import pass_difficulty


SQUADS = {
    "RED": [
        {"id": "RED-7", "team_id": "RED", "name": "Luca Moretti", "short_name": "Moretti", "starter": True},
        {"id": "RED-9", "team_id": "RED", "name": "Jonas Falk", "short_name": "Falk", "starter": True},
    ],
    "WHI": [
        {"id": "WHI-3", "team_id": "WHI", "name": "Sam Whitaker", "short_name": "Whitaker", "starter": True},
    ],
}
META = {"lineups": {"RED": ["RED-7", "RED-9"], "WHI": ["WHI-3"]},
        "attack_direction": {"1": {"RED": 1, "WHI": -1}}}


def event(i, t, kind="pass", team="RED", player="RED-7", **kwargs):
    return {"id": i, "t": float(t), "period": 1, "minute": int(t // 60), "second": int(t % 60),
            "type": kind, "team_id": team, "player_id": player, **kwargs}


def sample_events():
    return [
        event(1, 0, start={"x": 20, "y": 34}, end={"x": 50, "y": 34}, outcome="complete",
              frame={"players": [{"id": "RED-7", "x": 20, "y": 34}, {"id": "WHI-3", "x": 70, "y": 34}]}),
        event(2, 5, "dribble", player="RED-7", related_player_id="WHI-3", outcome="won",
              start={"x": 50, "y": 34}, end={"x": 55, "y": 34}),
        event(3, 10, "pass", team="WHI", player="WHI-3", start={"x": 70, "y": 34}, end={"x": 55, "y": 34}, outcome="incomplete"),
        event(4, 15, "shot", team="RED", player="RED-9", start={"x": 90, "y": 34}, outcome="saved", xg=0.4),
    ]


def test_pass_difficulty_formula_and_pressure_cap():
    e = event(1, 0, start={"x": 20, "y": 34}, end={"x": 50, "y": 34}, outcome="complete",
              frame={"players": [{"id": "WHI-3", "x": 51, "y": 34}]})
    # 25*30/45 + 25*30/30 + 20*(.5/3) + 20*0 + 10*0
    assert pass_difficulty(e, META) == 45.0
    pressured = copy.deepcopy(e)
    pressured["under_pressure"] = True
    pressured["end"] = {"x": 95, "y": 34}
    pressured["frame"]["players"] = ([{"id": f"WHI-{i}", "x": x, "y": 34}
                                         for i, x in enumerate((40, 50, 60, 70))] +
                                        [{"id": f"WHI-{i}", "x": 95, "y": 34} for i in range(4, 7)])
    assert pass_difficulty(pressured, META) == 100.0


def test_metric_value_matches_player_stats():
    engine = StatsEngine(sample_events(), SQUADS, META)
    for e in sample_events():
        engine.ingest(e)
    stats = engine.player_stats("RED-7")
    for key in STATS_KEYS:
        expected = stats[key]
        if isinstance(expected, dict):
            expected = expected["difficulty"]
        assert engine.metric_value("RED-7", key) == expected
    assert engine.metric_value("RED-7", "dribbles_won_vs", against="WHI-3") == 1


def test_rebuild_matches_incremental_ingest_at_seek_time():
    events = sample_events()
    incremental = StatsEngine(events, SQUADS, META)
    for e in events:
        if e["t"] <= 10:
            incremental.ingest(e)
    rebuilt = StatsEngine(events, SQUADS, META)
    rebuilt.rebuild(10)
    assert rebuilt.snapshot() == incremental.snapshot()
    assert rebuilt.player_stats("RED-7") == incremental.player_stats("RED-7")


def test_queries_do_not_leak_future_events():
    events = sample_events()
    engine = StatsEngine(events, SQUADS, META)
    engine.ingest(events[0])
    before = engine.snapshot()
    stats = engine.player_stats("RED-7")
    assert stats["passes"] == 1
    assert engine.t == 0
    assert before["possession"]["match"]["WHI"] == 0
    assert engine.key_moments() == []


def test_snapshot_indexes_are_normalized_and_quiet_windows_match_spec():
    engine = StatsEngine(sample_events(), SQUADS, META)
    for e in sample_events():
        engine.ingest(e)
    snapshot = engine.snapshot()
    assert sum(snapshot["control"].values()) == 100
    assert sum(snapshot["win_prob"].values()) == 1.0
    assert engine.quiet_window({"type": "throw_in"}) == 6
    assert engine.quiet_window({"type": "half_time"}) == float("inf")
    assert engine.quiet_window({"type": "carry"}) is None


def test_var_disallowed_goal_is_removed_from_score_and_player_totals():
    events = [
        event(1, 0, "goal", player="RED-9", outcome="goal"),
        event(2, 10, "goal", player="RED-9", outcome="goal"),
        event(3, 12, "var_decision", team=None, player=None,
              var={"check": "offside", "decision": "goal_disallowed"}),
    ]
    engine = StatsEngine(events, SQUADS, META)
    for e in events:
        engine.ingest(e)
    assert engine.metric_value("RED", "score") == 1
    assert engine.player_stats("RED-9")["goals"] == 1
