"""Booth: wires MatchData, MatchState, StatsEngine, BoothBoard, MatchClock and the agent runtime."""
from __future__ import annotations

import logging
from typing import Any

from . import llm
from .board import BoothBoard
from .clock import MatchClock
from .state import MatchData, MatchState
from .ws import hub

log = logging.getLogger("spotter.booth")
RECENT_EVENTS_S = 6.0  # events re-sent on connect/seek so the pitch has frames around display time


class NullAgents:
    async def on_event(self, e: dict, alerts: list[dict]) -> None: ...
    async def on_tick(self) -> None: ...
    async def reset(self) -> None: ...
    async def on_settings_changed(self, changed: set[str]) -> None: ...
    async def add_directive(self, text: str) -> Any: return None
    async def remove_directive(self, directive_id: str) -> None: ...
    async def remove_card(self, card_id: str) -> bool: return False
    async def say_now(self, card_id: str) -> bool: return False


class Booth:
    def __init__(self) -> None:
        from .stats.engine import StatsEngine

        self.data = MatchData()
        self.state = MatchState(self.data)
        self.state.reset()
        self.stats = StatsEngine(self.data.events, self.data.squads, self.data.meta)
        self.board = BoothBoard(self.broadcast)
        self.clock = MatchClock(self)
        self.agents: Any = NullAgents()
        self.state.cost_cap_reached = llm.ledger.cap_reached
        llm.ledger.on_cap(self._on_cap)

    def _on_cap(self) -> None:
        self.state.cost_cap_reached = True

    async def broadcast(self, msg: dict) -> None:
        await hub.broadcast(msg)

    async def trace(self, agent: str, action: str, detail: str) -> None:
        await self.broadcast({"type": "trace", "t": round(self.state.t, 1), "agent": agent, "action": action,
                              "detail": detail})

    def stats_msg(self) -> dict:
        return {"type": "stats", **self.stats.snapshot()}

    async def broadcast_stats(self) -> None:
        await self.broadcast(self.stats_msg())

    async def on_event(self, e: dict) -> None:
        self.state.apply(e)
        alerts = self.stats.ingest(e) or []
        await self.broadcast({"type": "event", "event": e})
        await self.agents.on_event(e, alerts)

    async def on_tick(self) -> None:
        await self.agents.on_tick()

    async def seek(self, t: float) -> None:
        """§8: clear board queue and audio, rebuild stats to t, agents resume with match-so-far context."""
        self.board.clear()
        self.state.reset()
        idx = self.data.index_at(t)
        for e in self.data.events[:idx]:
            self.state.apply(e)
        self.state.t, self.state.next_idx = t, idx
        self.stats.rebuild(t)
        await self.agents.reset()  # after state.t is set: periodic wake-ups are scheduled from the new time
        await self.broadcast({"type": "reset", "t": t})
        for msg in self.initial_messages():
            await self.broadcast(msg)

    def initial_messages(self) -> list[dict]:
        s = self.state
        msgs: list[dict] = [
            {"type": "instance", "instance": s.instance.model_dump()},
            {"type": "directive", "directives": [d.model_dump() for d in s.instance.directives]},
            s.clock_msg(self.clock.speed, self.clock.paused),
            self.stats_msg(),
        ]
        for a, st in s.agent_status.items():
            msgs.append({"type": "agent_status", "agent": a, **st})
        lo = max(0, self.data.index_at(s.t - RECENT_EVENTS_S) - 1)
        for e in self.data.events[lo:s.next_idx]:
            msgs.append({"type": "event", "event": e})
        for c in sorted(self.board.cards.values(), key=lambda c: c.created_t):
            msgs.append({"type": "card", "card": c.model_dump()})
        return msgs

    async def set_agent_status(self, agent: str, status: str, last_ms: int | None = None) -> None:
        st = self.state.agent_status[agent]
        st["status"] = status
        if last_ms is not None:
            st["last_ms"] = last_ms
        await self.broadcast({"type": "agent_status", "agent": agent, **st})
