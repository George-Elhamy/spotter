"""AgentRuntime: wires Dispatcher, proposers, Verifier, Producer, Narrator and Caller to the Booth.

Card lifecycle (§7.1): proposed → verifying → (rejected → revising → verifying) → verified → (skipped | queued)
→ rendering → ready → airing → aired; also expired / removed / discarded (failed twice).
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..models import Card
from ..tools.match_tools import build_tools
from . import proposers
from .caller import Caller
from .dispatcher import Dispatcher
from .producer import Producer
from .workflow import CardMsg, build_card_workflow

if TYPE_CHECKING:
    from ..booth import Booth

log = logging.getLogger("spotter.runtime")
RENDER_SETTINGS = {"language", "audience", "energy", "tone", "perspective", "focus_player_id"}


class AgentRuntime:
    def __init__(self, booth: "Booth") -> None:
        self.booth = booth
        self.tools = build_tools(booth)
        self.metric_names = sorted(getattr(booth.stats, "METRICS", {}).keys())
        self.producer = Producer(self)
        self.caller = Caller(self)
        self.dispatcher = Dispatcher(self)

    # ---------------------------------------------------------------- booth hooks
    async def on_event(self, e: dict, alerts: list[dict]) -> None:
        self.producer.on_event(e)
        self.dispatcher.on_event(e, alerts)
        await self.caller.on_event(e)

    async def on_tick(self) -> None:
        await self.dispatcher.tick()
        await self.producer.tick()
        await self.caller.tick()

    async def on_play(self) -> None:
        # never start silent: an opening/rejoin line as soon as play starts
        if self.producer.speaking_until == 0 or self.producer.speaking_until < self.producer.display_now() - 5:
            asyncio.create_task(self.caller.intro())

    async def reset(self) -> None:
        self.dispatcher.reset()
        self.producer.reset()
        self.caller.reset()
        for a in self.booth.state.agent_status:
            muted = a in self.booth.state.instance.muted_agents
            self.booth.state.agent_status[a]["status"] = "muted" if muted else "idle"

    async def on_settings_changed(self, changed: set[str]) -> None:
        if changed & RENDER_SETTINGS:
            await self.producer.rerender_all()
        if "focus_player_id" in changed and self.booth.state.instance.focus_player_id:
            pid = self.booth.state.instance.focus_player_id
            await self.dispatcher.wake("dossier", {"event": None, "key": f"focus:{pid}",
                                                   "reason": f"showrunner set focus player {self.booth.data.name(pid)}"},
                                       force=True)

    async def add_directive(self, text: str):
        return await self.producer.add_directive(text)

    async def remove_directive(self, directive_id: str) -> None:
        await self.producer.remove_directive(directive_id)

    async def remove_card(self, card_id: str) -> bool:
        return await self.producer.remove(card_id)

    async def say_now(self, card_id: str) -> bool:
        return await self.producer.say_now(card_id)

    # ---------------------------------------------------------------- card lifecycle
    async def run_proposer(self, agent: str, trigger: dict) -> None:
        card = await proposers.propose(self, agent, trigger)
        if card is None:
            await self.booth.trace(agent, "pass", f"nothing worth saying ({trigger['reason'][:60]})")
            return
        await self.lifecycle(card, trigger)

    async def lifecycle(self, card: Card, trigger: dict) -> None:
        """Runs the card through the Agent Framework workflow (Verify → Revise? → ProducerFit → Narrate)."""
        await build_card_workflow(self).run(CardMsg(card, trigger))
