"""Producer (spec §7.5, §8): audience fit, ranking loop, quiet-window airing, say-now, directives, adaptation.

Also the server-side audio scheduler: never overlap; calls first, say-now next, cards only in quiet windows.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
import re
import time
from typing import TYPE_CHECKING

from .. import config, llm
from ..models import Card, Directive
from . import prompts
from .narrator import narrate, speak

if TYPE_CHECKING:
    from .runtime import AgentRuntime

log = logging.getLogger("spotter.producer")
RANK_EVERY_S = 0.5
LONG_WINDOW_S = 40
PENDING = ("verified", "queued", "rendering", "ready")
TOPIC_WORDS = {"stat": ("stat", "stats", "number", "numbers", "data"), "tactical": ("tactic", "tactics", "tactical", "shape", "press"),
               "background": ("background", "history", "dossier", "season", "form"), "story": ("story", "stories", "storyline", "narrative")}


class Producer:
    def __init__(self, rt: "AgentRuntime") -> None:
        self.rt = rt
        self._dir_ids = itertools.count(1)
        self._speech_ids = itertools.count(1)
        self.reset()

    def reset(self) -> None:
        self.speaking_until = 0.0  # display-time when the last scheduled line ends
        self.window: list[float] | None = None  # [start, end] in display time
        self.airing: dict[str, float] = {}  # card id → display time it finishes
        self.say_now_ids: list[str] = []
        self.removals: list[tuple[float, str]] = []
        self._last_rank = 0.0

    # ------------------------------------------------------------ helpers
    @property
    def booth(self):
        return self.rt.booth

    def display_now(self) -> float:
        return self.booth.state.t - config.DISPLAY_DELAY_S

    def _span(self, dur_ms: int) -> float:
        return dur_ms / 1000 * max(1.0, self.booth.clock.speed)

    async def emit_speech(self, kind: str, card_id: str | None, text: str, subtitle_en: str | None,
                          audio_url: str | None, play_at: float, dur_ms: int, agent: str) -> float:
        if kind == "call":
            if play_at < self.display_now() - 3:  # §8: drop calls > 3 s stale
                return play_at
        else:
            play_at = max(play_at, self.speaking_until + 0.3, self.display_now() + 0.3)
        self.speaking_until = max(self.speaking_until, play_at) + self._span(dur_ms)
        sid = f"s_{next(self._speech_ids):04d}"
        await self.booth.broadcast({"type": "speech", "id": sid, "kind": kind, "card_id": card_id, "text": text,
                                    "subtitle_en": subtitle_en, "audio_url": audio_url, "play_at_t": round(play_at, 2),
                                    "duration_ms": dur_ms})
        self.booth.board.log_aired(play_at, kind, card_id, agent, text, self.booth.state.instance.language)
        return play_at

    # ------------------------------------------------------------ card flow
    async def fit(self, card: Card) -> tuple[bool, str, int]:
        inst = self.booth.state.instance
        for d in inst.directives:
            if d.type == "avoid_topic" and self._topic_match(card, d.target):
                return False, f"showrunner: avoid {d.target}", 0
        if llm.is_degraded() or llm.ledger.cap_reached:
            return True, "code-only ranking (LLM degraded)", 0
        user = json.dumps({"card": card.text, "category": card.category, "agent": card.agent,
                           "settings": inst.model_dump(include={"language", "audience", "perspective", "energy", "tone"}),
                           "focus_player": self.booth.data.name(inst.focus_player_id) if inst.focus_player_id else None,
                           "directives": [f"{d.type}:{d.target}" for d in inst.directives]}, ensure_ascii=False)
        try:
            out = llm.parse_json(await llm.complete(
                "producer", "nano", prompts.PRODUCER_FIT, user, timeout=10,
                cache_parts=[card.text, inst.audience, inst.perspective, inst.focus_player_id,
                             sorted(f"{d.type}:{d.target}" for d in inst.directives)]))
            return bool(out.get("fit", True)), str(out.get("reason") or "")[:80], int(out.get("priority_adjust") or 0)
        except (llm.LLMUnavailable, ValueError, AttributeError, TypeError):
            return True, "code-only ranking (fit check unavailable)", 0

    async def fit_and_queue(self, card: Card) -> bool:
        """Audience fit for a verified card → queued (True) or skipped (False)."""
        ok, reason, adj = await self.fit(card)
        board = self.booth.board
        if card.status != "verified":  # removed/expired meanwhile
            return False
        if not ok:
            await board.set_status(card, "skipped", producer={"fit": False, "reason": reason, "score": None})
            await self.booth.trace("producer", "skipped", f"{card.id}: {reason}")
            return False
        card.priority = max(1, min(5, card.priority + adj))
        await board.set_status(card, "queued", producer={"fit": True, "reason": reason, "score": self.score(card)})
        return True

    async def render(self, card: Card) -> None:
        board = self.booth.board
        inst = self.booth.state.instance
        if card.status not in ("queued", "ready", "rendering"):
            return
        await board.set_status(card, "rendering")
        line = await narrate(self.rt, card)
        if card.status != "rendering":
            return
        if line is None:
            await board.set_status(card, "skipped", producer={"reason": "narration failed number check"})
            return
        audio_url, dur = await speak(self.rt, line, inst, card.agent)
        if card.status != "rendering":
            return
        await board.set_status(card, "ready", render={"line": line, "language": inst.language, "audio_url": audio_url,
                                                      "duration_ms": dur})
        if card.id in self.say_now_ids:
            await self.air(card)

    async def air(self, card: Card) -> None:
        if card.id in self.say_now_ids:
            self.say_now_ids.remove(card.id)
        inst = self.booth.state.instance
        subtitle = card.text if card.render.language == "ar" else None
        play_at = await self.emit_speech("card", card.id, card.render.line or card.text, subtitle, card.render.audio_url,
                                         self.display_now() + 0.3, card.render.duration_ms or 3000, card.agent)
        self.airing[card.id] = play_at + self._span(card.render.duration_ms or 3000)
        await self.booth.board.set_status(card, "airing")
        await self.booth.trace("producer", "airing", f"{card.id} ({card.agent}) score {card.producer.score} lang {inst.language}")

    async def rerender_all(self) -> None:
        for c in self.booth.board.with_status("queued", "ready"):
            asyncio.create_task(self.render(c))

    # ------------------------------------------------------------ ranking
    def _topic_match(self, card: Card, target: str) -> bool:
        t = target.lower()
        if t in (card.category, card.agent):
            return True
        for cat, words in TOPIC_WORDS.items():
            if t in words and cat == card.category:
                return True
        return len(t) > 3 and t in card.text.lower()

    def score(self, card: Card) -> float:
        st = self.booth.state
        inst = st.instance
        s = 10.0 * card.priority
        try:
            inv = self.booth.stats.recent_involvement(st.t - 10)
        except Exception:  # noqa: BLE001
            inv = {}
        if set(card.player_ids) & set(inv.get("player_ids") or []):
            s += 25
        if card.team_id and card.team_id == inv.get("team_in_possession") and inv.get("final_third"):
            s += 10
        focus = {d.target for d in inst.directives if d.type == "focus_player"} | {inst.focus_player_id}
        if set(card.player_ids) & focus:
            s += 30
        for d in inst.directives:
            if d.type == "more_topic" and self._topic_match(card, d.target):
                s += 15
            elif d.type == "less_topic" and self._topic_match(card, d.target):
                s -= 15
        s -= min(20.0, (st.t - card.created_t) / max(card.ttl_s, 1) * 20)
        for a in self.booth.board.with_status("aired", "airing"):
            if a.status == "airing" or self._recently_aired(a, 60):
                if a.agent == card.agent:
                    s -= 10
                if set(a.player_ids) & set(card.player_ids):
                    s -= 15
        return round(s, 1)

    def _recently_aired(self, card: Card, within: float) -> bool:
        end = self.airing.get(card.id)
        return end is not None and self.display_now() - end < within

    async def tick(self) -> None:
        now = time.monotonic()
        if now - self._last_rank < RANK_EVERY_S:
            return
        self._last_rank = now
        st = self.booth.state
        board = self.booth.board
        disp = self.display_now()
        # finish airing cards
        for cid, end in list(self.airing.items()):
            c = board.get(cid)
            if c and c.status == "airing" and disp >= end:
                await board.set_status(c, "aired")
        # expire + rescore
        for c in board.with_status(*PENDING):
            if st.t > c.created_t + c.ttl_s and c.id not in self.say_now_ids:
                await board.set_status(c, "expired")
                await self.booth.trace("producer", "expired", f"{c.id} TTL {c.ttl_s:.0f}s passed")
                continue
            if c.status in ("queued", "ready"):
                new = self.score(c)
                if c.producer.score is None or abs(new - c.producer.score) >= 2:
                    await board.set_status(c, c.status, producer={"score": new})
        # expire directives
        live = [d for d in st.instance.directives if d.expires_t is None or d.expires_t > st.t]
        if len(live) != len(st.instance.directives):
            st.instance.directives = live
            await self.broadcast_directives()
        # air in quiet windows
        if any(board.get(cid) and board.get(cid).status == "airing" for cid in self.airing):
            return
        if self.window and disp < self.window[1] - 1.0:
            start, end = self.window
            play_at = max(start + 0.8, self.speaking_until + 0.3, disp)
            remaining = end - play_at
            ready = sorted(board.with_status("ready"), key=lambda c: -(c.producer.score or 0))
            long_window = end - start >= LONG_WINDOW_S
            for c in ready:
                if self._span(c.render.duration_ms or 3000) <= remaining or (long_window and c is ready[0]):
                    if not long_window:
                        self.window = None
                    await self.air(c)
                    break
        elif self.window:
            self.window = None

    def on_event(self, e: dict) -> None:
        try:
            w = self.booth.stats.quiet_window(e)
        except Exception:  # noqa: BLE001
            w = None
        if w:
            end = e["t"] + (w if w != float("inf") else 120)
            self.window = [e["t"], end] if not self.window else [self.window[0], max(self.window[1], end)]

    # ------------------------------------------------------------ human controls
    async def remove(self, card_id: str) -> bool:
        c = self.booth.board.get(card_id)
        if not c or c.status in ("aired", "expired", "removed", "discarded", "skipped"):
            return False
        await self.booth.board.set_status(c, "removed")
        await self.booth.trace("showrunner", "removed", f"{c.id} ({c.category})")
        t = self.booth.state.t
        self.removals = [(rt, cat) for rt, cat in self.removals if t - rt <= 300] + [(t, c.category)]
        n = sum(1 for _, cat in self.removals if cat == c.category)
        inst = self.booth.state.instance
        if n >= 3 and not any(d.type == "less_topic" and d.target == c.category for d in inst.directives):
            d = Directive(id=f"d_{next(self._dir_ids)}", type="less_topic", target=c.category, expires_t=t + 600,
                          source="auto", text=f"auto: you removed {n} {c.category} cards")
            inst.directives.append(d)
            await self.broadcast_directives()
            await self.booth.trace("producer", "adapted", d.text + f" → less_topic:{c.category}")
        return True

    async def say_now(self, card_id: str) -> bool:
        c = self.booth.board.get(card_id)
        if not c or c.status not in PENDING:
            return False
        await self.booth.trace("showrunner", "say_now", c.id)
        if c.status == "ready":
            await self.air(c)
        else:
            self.say_now_ids.append(c.id)
            if c.status == "verified":
                c.status = "queued"
                await self.render(c)
        return True

    async def broadcast_directives(self) -> None:
        await self.booth.broadcast({"type": "directive",
                                    "directives": [d.model_dump() for d in self.booth.state.instance.directives]})

    async def add_directive(self, text: str) -> Directive | None:
        data, st = self.booth.data, self.booth.state
        parsed = None
        if not llm.ledger.cap_reached:
            roster = "; ".join(f"{p['id']} {p['name']}" for p in data.players.values())
            try:
                parsed = llm.parse_json(await llm.complete("directive_parser", "nano",
                                                           prompts.DIRECTIVE_PARSER.format(players=roster), text,
                                                           cache_parts=[text], timeout=8))
            except (llm.LLMUnavailable, ValueError):
                parsed = None
        if not isinstance(parsed, dict) or not parsed.get("type"):
            parsed = self._parse_fallback(text)
        if not parsed:
            return None
        typ, target = parsed["type"], str(parsed.get("target") or "")
        if typ == "focus_player" and target not in data.players:
            return None
        dur = parsed.get("duration_min")
        d = Directive(id=f"d_{next(self._dir_ids)}", type=typ, target=target,
                      expires_t=st.t + float(dur) * 60 if dur else None, source="human", text=text[:60])
        st.instance.directives.append(d)
        if typ == "mute_agent" and target in st.agent_status and target not in st.instance.muted_agents:
            st.instance.muted_agents.append(target)  # type: ignore[arg-type]
            await self.booth.set_agent_status(target, "muted")
        await self.broadcast_directives()
        await self.booth.trace("producer", "directive", f"{text!r} → {typ}:{target}")
        if typ == "focus_player":
            await self.rt.dispatcher.wake("dossier", {"reason": f"showrunner set focus on {data.name(target)}",
                                                      "key": f"focus:{target}", "event": None}, force=True)
        return d

    def _parse_fallback(self, text: str) -> dict | None:
        low = text.lower()
        for p in self.booth.data.players.values():
            if p["short_name"].lower() in low:
                if "focus" in low or "follow" in low or "watch" in low:
                    return {"type": "focus_player", "target": p["id"]}
        for cat, words in TOPIC_WORDS.items():
            if any(re.search(rf"\b{w}\b", low) for w in words):
                if re.search(r"\b(no|avoid|stop|don't)\b", low):
                    return {"type": "avoid_topic", "target": cat}
                if re.search(r"\b(less|fewer)\b", low):
                    return {"type": "less_topic", "target": cat}
                return {"type": "more_topic", "target": cat}
        return None

    async def remove_directive(self, directive_id: str) -> None:
        inst = self.booth.state.instance
        inst.directives = [d for d in inst.directives if d.id != directive_id]
        await self.broadcast_directives()
