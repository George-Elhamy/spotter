"""Headless end-to-end run of a short match window (spec §13 dev tips) — no browser, no WebSocket client.

Run from backend/:  .venv/bin/python -m scripts.run_window --minute 17 --seconds 90 --speed 2 [--voice] [--lang ar ...]
Prints the trace, speech lines and final board. AI voice is OFF unless --voice.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter

from app import llm
from app.booth import Booth


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minute", type=float, default=17)
    ap.add_argument("--seconds", type=float, default=60, help="wall seconds to run")
    ap.add_argument("--speed", type=int, default=1)
    ap.add_argument("--voice", action="store_true")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--audience", default="analyst")
    ap.add_argument("--perspective", default="neutral")
    ap.add_argument("--energy", type=int, default=3)
    ap.add_argument("--directive", default=None)
    ap.add_argument("--quiet", action="store_true", help="hide event/clock/stats messages")
    args = ap.parse_args()

    booth = Booth()
    from app.agents.runtime import AgentRuntime

    booth.agents = AgentRuntime(booth)
    inst = booth.state.instance
    inst.ai_voice, inst.language, inst.audience = args.voice, args.lang, args.audience
    inst.perspective, inst.energy = args.perspective, args.energy
    counts: Counter = Counter()

    async def show(msg: dict) -> None:
        typ = msg["type"]
        counts[typ] += 1
        if typ == "trace":
            print(f"  [trace {msg['t']:7.1f}] {msg['agent']:<12} {msg['action']:<10} {msg['detail']}")
        elif typ == "speech":
            print(f"  [speech @{msg['play_at_t']:7.1f}] {msg['kind']:<4} {msg['text']}"
                  + (f"  // {msg['subtitle_en']}" if msg.get("subtitle_en") else "") + (" 🔊" if msg.get("audio_url") else ""))
        elif typ == "card" and msg["card"]["status"] in ("proposed",):
            c = msg["card"]
            print(f"  [card {c['id']} {c['agent']}] {c['text']}  claims={json.dumps([(x['metric'], x['value']) for x in c['claims']])}")
        elif typ == "event" and not args.quiet and msg["event"]["type"] in ("goal", "card", "shot", "substitution", "var_decision"):
            e = msg["event"]
            print(f"  [event {e['t']:7.1f}] {e['minute']}' {e['type']} {booth.data.name(e.get('player_id'))}")

    booth.broadcast = show  # type: ignore[method-assign]
    booth.board._broadcast = show
    await booth.seek(booth.data.seek_t(args.minute))
    if args.directive:
        print("directive →", await booth.agents.add_directive(args.directive))
    await booth.clock.set_speed(args.speed)
    booth.clock.start()
    await booth.clock.play()
    print(f"== running {args.seconds}s wall from {args.minute}' at {args.speed}× (voice={'on' if args.voice else 'off'}, lang={args.lang})")
    await asyncio.sleep(args.seconds)
    await booth.clock.pause()
    print("\n== board")
    for c in sorted(booth.board.cards.values(), key=lambda c: c.created_t):
        print(f"  {c.id} {c.status:<10} {c.agent:<11} score={c.producer.score} | {c.text[:90]}"
              + (f"\n      ↳ {c.render.line}" if c.render.line else "")
              + (f"\n      ✗ {c.verifier.reason}" if c.verifier.ok is False else "")
              + (f"\n      skip: {c.producer.reason}" if c.status == "skipped" else ""))
    print(f"== msgs {dict(counts)}\n== cost ledger ${llm.ledger.total:.4f}  by agent: "
          + ", ".join(f"{k}=${v['usd']:.4f}/{v['calls']}" for k, v in llm.ledger.data["by_agent"].items()))


asyncio.run(main())
