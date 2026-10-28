"""Smoke test the Foundry deployments + Azure Speech through app.llm (costs < $0.001).

Run from backend/:  .venv/bin/python -m scripts.smoke_llm [--tts]
"""
from __future__ import annotations

import asyncio
import sys

from app import config, llm


async def main() -> None:
    print(f"endpoint={config.AZURE_OPENAI_ENDPOINT!r} mini={config.MODEL_MINI} nano={config.MODEL_NANO} "
          f"api_version={config.AZURE_OPENAI_API_VERSION} llm_enabled={config.LLM_ENABLED} tts_enabled={config.TTS_ENABLED}")
    before = llm.ledger.total
    for kind in ("nano", "mini"):
        out = await llm.complete("smoke", kind, "Reply with JSON only.", 'Return {"ok": true, "model": "<your name>"}.')
        print(kind, "→", out)

    from agent_framework import tool

    @tool
    def get_score() -> dict:
        """Current match score."""
        return {"RED": 1, "WHI": 1, "minute": 38}

    out = await llm.run_agent("smoke_agent", "Answer in JSON {\"score\": \"x-y\"} using the tool.", [get_score],
                              "What is the score?", kind="nano", effort="minimal")
    print("agent →", out)
    if "--tts" in sys.argv:
        for lang, text in (("en", "Moretti skips past Whitaker!"), ("es", "¡Moretti se va de Whitaker!")):
            print("tts", lang, "→", await llm.synthesize(text, lang, 5))
    print(f"cost this run ${llm.ledger.total - before:.6f}; ledger total ${llm.ledger.total:.6f}")


asyncio.run(main())
