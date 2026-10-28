"""WebSocket fan-out (spec §10): one socket, server → client."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("spotter.ws")


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def send(self, ws: WebSocket, msg: dict[str, Any]) -> None:
        await ws.send_text(json.dumps(msg, ensure_ascii=False, default=str))

    async def broadcast(self, msg: dict[str, Any]) -> None:
        if not self.clients:
            return
        text = json.dumps(msg, ensure_ascii=False, default=str)
        clients = list(self.clients)
        results = await asyncio.gather(*(c.send_text(text) for c in clients), return_exceptions=True)
        for c, r in zip(clients, results):
            if isinstance(r, Exception):
                self.disconnect(c)


hub = Hub()
