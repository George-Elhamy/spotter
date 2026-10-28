"""BoothBoard — the shared blackboard (spec §3, §7.1). Agents never call each other; they read/write here."""
from __future__ import annotations

import itertools
from typing import Any, Awaitable, Callable

from .models import TERMINAL_STATUSES, Card

Broadcast = Callable[[dict], Awaitable[None]]


class BoothBoard:
    def __init__(self, broadcast: Broadcast) -> None:
        self._broadcast = broadcast
        self.cards: dict[str, Card] = {}
        self.audit: list[dict[str, Any]] = []
        self._ids = itertools.count(1)

    def new_id(self) -> str:
        return f"c_{next(self._ids):04d}"

    def clear(self, keep_aired_before: float | None = None) -> None:
        """On seek: drop pending/rejected cards. Aired cards created before the new time stay as history
        (shown on the board and used for dedupe); jumping back removes the ones from "the future"."""
        if keep_aired_before is None:
            self.cards = {}
            return
        self.cards = {cid: c for cid, c in self.cards.items()
                      if c.status == "aired" and c.created_t <= keep_aired_before}

    async def put(self, card: Card) -> Card:
        self.cards[card.id] = card
        await self._broadcast({"type": "card", "card": card.model_dump()})
        return card

    async def set_status(self, card: Card, status: str, **patch: Any) -> Card:
        """Update status (+ nested verifier/producer/render patches) and broadcast."""
        card.status = status  # type: ignore[assignment]
        for section in ("verifier", "producer", "render"):
            if section in patch:
                for k, v in patch.pop(section).items():
                    setattr(getattr(card, section), k, v)
        for k, v in patch.items():
            setattr(card, k, v)
        return await self.put(card)

    def get(self, card_id: str) -> Card | None:
        return self.cards.get(card_id)

    def active(self) -> list[Card]:
        return [c for c in self.cards.values() if c.status not in TERMINAL_STATUSES]

    def with_status(self, *statuses: str) -> list[Card]:
        return [c for c in self.cards.values() if c.status in statuses]

    def aired(self) -> list[Card]:
        return sorted(self.with_status("aired"), key=lambda c: c.created_t)

    def recent(self, n: int = 12) -> list[dict[str, Any]]:
        """Compact view for get_recent_cards(): latest cards with status, newest first."""
        cards = sorted(self.cards.values(), key=lambda c: c.created_t, reverse=True)[:n]
        return [{"id": c.id, "agent": c.agent, "status": c.status, "text": c.text, "player_ids": c.player_ids,
                 "created_t": c.created_t} for c in cards]

    def log_aired(self, t: float, kind: str, card_id: str | None, agent: str, text: str, language: str) -> None:
        self.audit.append({"t": round(t, 1), "kind": kind, "card_id": card_id, "agent": agent, "text": text,
                           "language": language})
