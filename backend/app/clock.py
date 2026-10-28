"""MatchClock (spec §8): server clock runs DISPLAY_DELAY_S ahead of what the screen shows."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .booth import Booth

log = logging.getLogger("spotter.clock")
TICK_S = 0.1


class MatchClock:
    def __init__(self, booth: "Booth") -> None:
        self.booth = booth
        self.speed: float = 1.0
        self.paused: bool = True
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="match-clock")

    async def _run(self) -> None:
        last = time.monotonic()
        last_clock = last_stats = 0.0
        b = self.booth
        while True:
            await asyncio.sleep(TICK_S)
            now = time.monotonic()
            dt, last = now - last, now
            async with self._lock:
                if not self.paused and b.state.t < b.data.duration_t + 5:
                    b.state.t += dt * self.speed
                    while b.state.next_idx < len(b.data.events) and b.data.events[b.state.next_idx]["t"] <= b.state.t:
                        e = b.data.events[b.state.next_idx]
                        b.state.next_idx += 1
                        try:
                            await b.on_event(e)
                        except Exception:  # noqa: BLE001 — never kill the clock
                            log.exception("on_event failed for %s", e.get("id"))
                try:
                    await b.on_tick()
                except Exception:  # noqa: BLE001
                    log.exception("on_tick failed")
            if now - last_clock >= 0.5:
                last_clock = now
                await b.broadcast(b.state.clock_msg(self.speed, self.paused))
            if now - last_stats >= 1.0:
                last_stats = now
                await b.broadcast_stats()

    async def play(self) -> None:
        self.paused = False
        await self.booth.agents.on_play()
        await self.booth.broadcast(self.booth.state.clock_msg(self.speed, self.paused))

    async def pause(self) -> None:
        self.paused = True
        await self.booth.broadcast(self.booth.state.clock_msg(self.speed, self.paused))

    async def set_speed(self, speed: float) -> None:
        self.speed = speed if speed in (1, 2, 5) else 1
        await self.booth.broadcast(self.booth.state.clock_msg(self.speed, self.paused))

    async def seek(self, minute: float) -> None:
        async with self._lock:
            await self.booth.seek(self.booth.data.seek_t(minute))
