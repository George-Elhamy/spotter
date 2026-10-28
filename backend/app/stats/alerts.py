"""Threshold and milestone alerts generated as events are ingested."""
from __future__ import annotations


def alert(engine, event: dict) -> list[dict]:
    return engine._alerts_for_event(event)
