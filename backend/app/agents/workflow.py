"""Card lifecycle as a Microsoft Agent Framework workflow (spec §3, §7.1).

    Verify ──ok──► ProducerFit ──fit──► Narrate (render + TTS → ready)
      │  ▲
  fail│  │revised card
      ▼  │
     Revise (proposer gets one attempt with the Verifier's reason; second failure → discarded)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from .. import llm
from ..models import Card
from . import proposers, verifier

if TYPE_CHECKING:
    from .runtime import AgentRuntime


@dataclass
class CardMsg:
    card: Card
    trigger: dict[str, Any]
    attempt: int = 0
    ok: bool = False
    reason: str = ""


class VerifyExecutor(Executor):
    def __init__(self, rt: "AgentRuntime") -> None:
        super().__init__(id="verifier")
        self.rt = rt

    @handler
    async def handle(self, msg: CardMsg, ctx: WorkflowContext[CardMsg]) -> None:
        board, card = self.rt.booth.board, msg.card
        await board.put(card)
        await board.set_status(card, "verifying")
        msg.ok, msg.reason = await verifier.verify(self.rt, card)
        if msg.ok:
            await board.set_status(card, "verified", verifier={"ok": True, "reason": msg.reason})
            await self.rt.booth.trace("verifier", "approved", f"{card.id}: {msg.reason[:100]}")
        else:
            await board.set_status(card, "rejected", verifier={"ok": False, "reason": msg.reason})
            await self.rt.booth.trace("verifier", "rejected", f"{card.id}: {msg.reason}")
            if msg.attempt > 0:
                await board.set_status(card, "discarded", verifier={"reason": f"failed twice: {msg.reason}"})
        await ctx.send_message(msg)


class ReviseExecutor(Executor):
    def __init__(self, rt: "AgentRuntime") -> None:
        super().__init__(id="revise")
        self.rt = rt

    @handler
    async def handle(self, msg: CardMsg, ctx: WorkflowContext[CardMsg]) -> None:
        board, card = self.rt.booth.board, msg.card
        await board.set_status(card, "revising")
        try:
            revised = await proposers.propose(self.rt, card.agent, msg.trigger, revision=(card, msg.reason))
        except llm.LLMUnavailable:
            revised = None
        await board.set_status(card, "discarded",
                               verifier={"reason": f"{msg.reason} → revised" if revised else msg.reason})
        if revised:
            revised.verifier.revision_of = card.id
            await ctx.send_message(CardMsg(revised, msg.trigger, attempt=1))


class ProducerFitExecutor(Executor):
    def __init__(self, rt: "AgentRuntime") -> None:
        super().__init__(id="producer_fit")
        self.rt = rt

    @handler
    async def handle(self, msg: CardMsg, ctx: WorkflowContext[CardMsg]) -> None:
        msg.ok = await self.rt.producer.fit_and_queue(msg.card)
        await ctx.send_message(msg)


class NarrateExecutor(Executor):
    def __init__(self, rt: "AgentRuntime") -> None:
        super().__init__(id="narrator")
        self.rt = rt

    @handler
    async def handle(self, msg: CardMsg, ctx: WorkflowContext[Any, Card]) -> None:
        await self.rt.producer.render(msg.card)
        await ctx.yield_output(msg.card)


def build_card_workflow(rt: "AgentRuntime"):
    verify, revise, fit, narrate = VerifyExecutor(rt), ReviseExecutor(rt), ProducerFitExecutor(rt), NarrateExecutor(rt)
    return (
        WorkflowBuilder(name="card_lifecycle", start_executor=verify, max_iterations=20)
        .add_edge(verify, fit, condition=lambda m: m.ok)
        .add_edge(verify, revise, condition=lambda m: not m.ok and m.attempt == 0)
        .add_edge(revise, verify)
        .add_edge(fit, narrate, condition=lambda m: m.ok)
        .build()
    )
