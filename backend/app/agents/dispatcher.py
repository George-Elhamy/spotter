"""Dispatcher (spec §7.2) — code, not an agent. Maps events to wake-ups with cooldowns, mutes, concurrency cap."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from typing import TYPE_CHECKING

from .. import llm
from ..models import AGENTS

if TYPE_CHECKING:
    from .runtime import AgentRuntime

log = logging.getLogger("spotter.dispatcher")
COOLDOWN = {"stats_scout": 45, "tactical": 90, "dossier": 60, "storyline": 90}
PERIODIC = {"stats_scout": 180, "tactical": 300, "storyline": 600}
CATEGORY = {"stats_scout": "stat", "tactical": "tactical", "dossier": "background", "storyline": "story"}
MAX_CONCURRENT = 3
PRIO = {"goal": 5, "card": 4, "var_decision": 4, "penalty_taken": 4, "substitution": 3, "alert": 3, "shot": 2}


class Dispatcher:
    def __init__(self, rt: "AgentRuntime") -> None:
        self.rt = rt
        self.sem = asyncio.Semaphore(MAX_CONCURRENT)
        self.tasks: set[asyncio.Task] = set()
        self.reset()

    def reset(self) -> None:
        t = self.rt.booth.state.t
        for task in self.tasks:
            task.cancel()
        self.tasks = set()
        self.last_wake = {a: -1e9 for a in AGENTS}
        # stagger periodic wakes so a fresh seek produces cards within seconds, not all at once
        self.last_periodic = {a: t - PERIODIC.get(a, 1e9) + 6 + 8 * i for i, a in enumerate(AGENTS)}
        self.pending: dict[str, tuple[int, dict]] = {}
        self.busy: set[str] = set()
        self.backoff = {a: 1.0 for a in AGENTS}
        self.seen_players: set[str] = set()
        self.duels: Counter = Counter()
        self.control_at_tactical: float | None = None
        self._last_swing_check = 0.0

    def _offer(self, agent: str, prio: int, trigger: dict) -> None:
        cur = self.pending.get(agent)
        if cur is None or prio >= cur[0]:
            self.pending[agent] = (prio, trigger)

    def _attack_third(self, e: dict) -> bool:
        end = e.get("end") or e.get("start")
        if not end or not e.get("team_id"):
            return False
        d = self.rt.booth.data.meta["attack_direction"][str(e["period"])][e["team_id"]]
        return end["x"] > 70 if d == "+x" else end["x"] < 35

    def on_event(self, e: dict, alerts: list[dict]) -> None:
        typ, pid = e["type"], e.get("player_id")
        ev = {"event": e, "key": f"ev:{e['id']}"}
        prio = PRIO.get(typ, 1)
        red_card = typ == "card" and e.get("card") in ("second_yellow", "red")
        if typ in ("shot", "goal", "card", "substitution"):
            self._offer("stats_scout", prio, {**ev, "reason": f"{typ} just happened"})
        if alerts:
            self._offer("stats_scout", 3, {**ev, "alerts": alerts, "key": f"al:{e['id']}",
                                           "reason": "new stats alerts: " + "; ".join(a.get("text", a.get("kind", "")) for a in alerts[:3])})
        if red_card or typ in ("substitution", "goal"):
            self._offer("tactical", prio, {**ev, "reason": f"{'red card' if red_card else typ} — shape/control may change"})
        if typ in ("goal", "card", "substitution") or (pid and pid not in self.seen_players and (
                typ == "shot" or (typ in ("pass", "carry", "dribble") and self._attack_third(e)))):
            reason = {"substitution": f"{self.rt.booth.data.name(pid)} came on"}.get(typ, f"{self.rt.booth.data.name(pid)} involved: {typ}")
            self._offer("dossier", prio if typ != "pass" else 1, {**ev, "reason": reason})
        if pid and typ in ("shot", "pass", "carry", "dribble"):
            self.seen_players.add(pid)
        if typ in ("goal", "card"):
            self._offer("storyline", prio, {**ev, "reason": f"{typ} — does it connect to an earlier thread?"})
        if typ in ("dribble", "duel", "tackle") and pid and e.get("related_player_id"):
            pair = tuple(sorted((pid, e["related_player_id"])))
            self.duels[pair] += 1
            if self.duels[pair] in (3, 5, 8):
                names = " vs ".join(self.rt.booth.data.name(p) for p in pair)
                self._offer("storyline", 3, {**ev, "reason": f"repeated duel pattern: {names} ({self.duels[pair]} times)"})

    async def tick(self) -> None:
        st = self.rt.booth.state
        t = st.t
        for a, every in PERIODIC.items():
            if t - self.last_periodic[a] >= every:
                self.last_periodic[a] = t
                self._offer(a, 1, {"event": None, "key": f"per:{a}:{int(t // every)}",
                                   "reason": f"periodic check ({every // 60} match-minutes)"})
        if time.monotonic() - self._last_swing_check > 2:
            self._last_swing_check = time.monotonic()
            red = float(self.rt.booth.stats.snapshot()["control"]["RED"])
            if self.control_at_tactical is None:
                self.control_at_tactical = red
            elif abs(red - self.control_at_tactical) > 12:
                self._offer("tactical", 3, {"event": None, "key": f"swing:{int(t // 30)}",
                                            "reason": f"control swing: Redmoor control {self.control_at_tactical:.0f} → {red:.0f}"})
        if llm.ledger.cap_reached or self.rt.booth.clock.paused:
            return
        for agent, (prio, trigger) in list(self.pending.items()):
            if self._blocked(agent):
                continue
            if t - self.last_wake[agent] < COOLDOWN[agent] * self.backoff[agent] or len(self.busy) >= MAX_CONCURRENT:
                continue
            del self.pending[agent]
            await self.wake(agent, trigger)

    def _blocked(self, agent: str) -> bool:
        inst = self.rt.booth.state.instance
        if agent in inst.muted_agents:
            self.pending.pop(agent, None)
            return True
        if any(d.type == "avoid_topic" and d.target in (CATEGORY[agent], agent) for d in inst.directives):
            return True
        return agent in self.busy

    async def wake(self, agent: str, trigger: dict, force: bool = False) -> None:
        if force and (self._blocked(agent) or llm.ledger.cap_reached):
            self._offer(agent, 5, trigger)
            return
        self.last_wake[agent] = self.rt.booth.state.t
        if agent == "tactical":
            self.control_at_tactical = float(self.rt.booth.stats.snapshot()["control"]["RED"])
        self.busy.add(agent)
        task = asyncio.create_task(self._run(agent, trigger))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, agent: str, trigger: dict) -> None:
        booth = self.rt.booth
        started = time.monotonic()
        try:
            async with self.sem:
                await booth.set_agent_status(agent, "thinking")
                await self.rt.run_proposer(agent, trigger)
            self.backoff[agent] = 1.0
            await booth.set_agent_status(agent, "idle", int((time.monotonic() - started) * 1000))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — §12.3: status error, back off, others continue
            self.backoff[agent] = min(4.0, self.backoff[agent] * 2)
            log.warning("%s failed: %s", agent, e)
            await booth.set_agent_status(agent, "error", int((time.monotonic() - started) * 1000))
            await booth.trace(agent, "error", f"{type(e).__name__}: {str(e)[:120]} (backing off ×{self.backoff[agent]:g})")
        finally:
            self.busy.discard(agent)
