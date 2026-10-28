"""FastAPI app: REST + WebSocket (spec §10) and the built frontend (spec §16)."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import cache, config, llm
from .booth import Booth
from .models import ControlRequest, DirectiveRequest, InstancePatch, MuteRequest
from .ws import hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("spotter")
booth: Booth


@asynccontextmanager
async def lifespan(app: FastAPI):
    global booth
    booth = Booth()
    try:
        from .agents.runtime import AgentRuntime

        booth.agents = AgentRuntime(booth)
    except ImportError as e:
        log.warning("agents runtime unavailable (%s); running without agents", e)
    booth.clock.start()
    log.info("Spotter up: %d events, LLM=%s TTS=%s CACHE_MODE=%s cost=$%.4f/%s", len(booth.data.events),
             config.LLM_ENABLED, config.TTS_ENABLED, config.CACHE_MODE, llm.ledger.total, config.COST_CAP_USD)
    yield


app = FastAPI(title="Spotter", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"ok": True, "t": round(booth.state.t, 1), "llm": config.LLM_ENABLED, "tts": config.TTS_ENABLED,
            "cache_mode": config.CACHE_MODE, "cost_usd": round(llm.ledger.total, 4),
            "cost_cap_usd": config.COST_CAP_USD, "cost_cap_reached": llm.ledger.cap_reached}


@app.get("/api/match/meta")
async def match_meta():
    return booth.data.meta_payload()


@app.post("/api/match/control")
async def match_control(req: ControlRequest):
    c = booth.clock
    if req.action == "play":
        await c.play()
    elif req.action == "pause":
        await c.pause()
    elif req.action == "speed":
        await c.set_speed(int(req.value or 1))
    elif req.action == "seek":
        await c.seek(float(req.value or 0))
    elif req.action == "seek_t":
        await c.seek_t(float(req.value or 0))
    return {"ok": True, "t": booth.state.t, "speed": c.speed, "paused": c.paused}


@app.get("/api/instance")
async def get_instance():
    return booth.state.instance.model_dump()


@app.patch("/api/instance")
async def patch_instance(patch: InstancePatch):
    inst = booth.state.instance
    changed = {k for k, v in patch.model_dump(exclude_unset=True).items() if getattr(inst, k) != v}
    for k in changed:
        setattr(inst, k, getattr(patch, k))
    if changed:
        await booth.broadcast({"type": "instance", "instance": inst.model_dump()})
        await booth.agents.on_settings_changed(changed)
    return inst.model_dump()


@app.post("/api/directive")
async def add_directive(req: DirectiveRequest):
    d = await booth.agents.add_directive(req.text)
    if d is None:
        raise HTTPException(422, "could not parse directive")
    return d.model_dump()


@app.delete("/api/directive/{directive_id}")
async def delete_directive(directive_id: str):
    await booth.agents.remove_directive(directive_id)
    return {"ok": True}


@app.post("/api/agents/{name}/mute")
async def mute_agent(name: str, req: MuteRequest):
    if name not in booth.state.agent_status:
        raise HTTPException(404, "unknown agent")
    muted = booth.state.instance.muted_agents
    if req.muted and name not in muted:
        muted.append(name)  # type: ignore[arg-type]
    elif not req.muted and name in muted:
        muted.remove(name)  # type: ignore[arg-type]
    await booth.set_agent_status(name, "muted" if req.muted else "idle")
    await booth.broadcast({"type": "instance", "instance": booth.state.instance.model_dump()})
    return {"ok": True}


@app.post("/api/cards/{card_id}/remove")
async def remove_card(card_id: str):
    if not await booth.agents.remove_card(card_id):
        raise HTTPException(404, "card not found or already final")
    return {"ok": True}


@app.post("/api/cards/{card_id}/say-now")
async def say_now(card_id: str):
    if not await booth.agents.say_now(card_id):
        raise HTTPException(404, "card not found or already final")
    return {"ok": True}


@app.get("/api/audio/{audio_id}.mp3")
async def audio(audio_id: str):
    if not audio_id.isalnum():
        raise HTTPException(400)
    path = cache.audio_path(audio_id)
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/audit")
async def audit():
    return JSONResponse(booth.board.audit)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        for msg in booth.initial_messages():
            await hub.send(ws, msg)
        while True:
            await ws.receive_text()  # client → server goes over REST; keep the socket open
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("ws error")
    finally:
        hub.disconnect(ws)


if config.STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        f = config.STATIC_DIR / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(config.STATIC_DIR / "index.html")
