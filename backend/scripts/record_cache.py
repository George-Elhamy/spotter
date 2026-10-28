"""Record the demo cache (spec §13) for one preset over the demo windows.

Run from backend/ (one process per preset, both can run in parallel):
  .venv/bin/python -m scripts.record_cache --preset en
  .venv/bin/python -m scripts.record_cache --preset ar
Writes LLM responses to app/data/cache/llm/ and audio to app/data/cache/audio/ (committed; deployed app runs replay).
"""
from __future__ import annotations

import argparse
import asyncio
import os

os.environ["CACHE_MODE"] = "record"

PRESETS = {
    "en": dict(name="EN Analyst", language="en", audience="analyst", perspective="neutral", energy=3, tone="neutral"),
    "es": dict(name="ES Casual Redmoor", language="es", audience="casual", perspective="RED", energy=5, tone="hype"),
}
# (jump minute, match seconds to run) — the windows used in the demo video and README test instructions
WINDOWS = [(17, 150), (37, 120), (51, 200), (60, 480), (87, 600)]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=PRESETS, required=True)
    ap.add_argument("--speed", type=int, default=1)
    ap.add_argument("--only", type=int, default=None, help="record a single window (jump minute)")
    args = ap.parse_args()

    from app import config, llm
    from app.agents.runtime import AgentRuntime
    from app.booth import Booth

    assert config.CACHE_MODE == "record"
    booth = Booth()
    booth.agents = AgentRuntime(booth)
    for k, v in PRESETS[args.preset].items():
        setattr(booth.state.instance, k, v)
    booth.state.instance.ai_voice = True

    async def quiet(msg: dict) -> None:
        if msg["type"] == "speech":
            print(f"  [{args.preset} @{msg['play_at_t']:7.1f}] {msg['kind']}: {msg['text']}", flush=True)

    booth.broadcast = quiet  # type: ignore[method-assign]
    booth.board._broadcast = quiet
    booth.clock.start()
    await booth.clock.set_speed(args.speed)
    for minute, secs in WINDOWS:
        if args.only is not None and minute != args.only:
            continue
        print(f"== {args.preset}: {minute}' for {secs}s match time", flush=True)
        await booth.clock.seek(minute)
        await booth.clock.play()
        await asyncio.sleep(secs / args.speed + 4)
        await booth.clock.pause()
        await asyncio.sleep(6)  # let in-flight agent runs land in the cache
    print(f"== done {args.preset}; ledger ${llm.ledger.total:.4f}")


asyncio.run(main())
