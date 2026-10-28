"""Integration checks for the deterministic generated match, when files are ready."""
import json
from pathlib import Path
import time

import pytest

from app.stats.engine import StatsEngine


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"
SCHEMA = ROOT / "app" / "generator" / "SCHEMA.md"
MATCH = DATA / "match_events.json"
SQUADS = DATA / "squads.json"


@pytest.mark.skipif(not (SCHEMA.exists() and MATCH.exists() and SQUADS.exists()),
                    reason="generated match and generator schema are not ready")
def test_generated_match_realism_and_calibration():
    match = json.loads(MATCH.read_text())
    squads = json.loads(SQUADS.read_text())
    events, meta = match["events"], match["meta"]
    engine = StatsEngine(events, squads, meta)

    engine.rebuild(15 * 60)
    assert engine.metric_value("RED-7", "dribbles_won_vs", against="WHI-3") >= 4

    engine.rebuild(float(meta.get("half_time_t", 45 * 60)))
    red_possession = engine.team_stats("RED", "half")["possession"]
    assert 50 <= red_possession <= 60

    first = engine.compare_periods("1-15", "25-37")
    assert first["25-37"]["WHI"]["possession"] > first["1-15"]["WHI"]["possession"]
    assert first["25-37"]["control"]["WHI"] > first["1-15"]["control"]["WHI"]

    calibration = StatsEngine(events, squads, meta)
    index = 0
    low_samples, late_samples = [], []
    def minute_t(minute: int) -> float:
        period = 1 if minute < 45 else 2
        return next(float(e["t"]) for e in events if e["period"] == period and e["minute"] >= minute)

    for minute in range(1, 87):
        sample_t = minute_t(minute)
        while index < len(events) and float(events[index]["t"]) <= sample_t:
            calibration.ingest(events[index])
            index += 1
        chaos = calibration._chaos_for_window(calibration._window_events("5min"))
        if 1 <= minute <= 15:
            low_samples.append(chaos)
        if 78 <= minute <= 86:
            late_samples.append(chaos)
    assert max(low_samples) < 35
    assert sum(late_samples) / len(late_samples) > 75
    assert sum(value > 75 for value in late_samples) / len(late_samples) >= 0.8

    full = StatsEngine(events, squads, meta)
    started = time.perf_counter()
    full.rebuild(float("inf"))
    elapsed = time.perf_counter() - started
    assert elapsed < 1.5
    assert sum(full.snapshot()["control"].values()) == 100
