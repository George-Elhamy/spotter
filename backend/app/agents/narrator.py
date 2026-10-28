"""Narrator (spec §7.6): neutral card → one spoken line for the instance settings, numbers preserved; then TTS."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from .. import llm
from ..models import Card, InstanceSettings
from . import prompts

if TYPE_CHECKING:
    from .runtime import AgentRuntime

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
AUDIENCE_HINT = {"casual": "simple words, emotion, no jargon", "analyst": "precise, tactical vocabulary welcome"}
PERSPECTIVE = {"neutral": "neutral", "RED": "a Redmoor Rovers fan broadcast", "WHI": "a Whitcliffe Athletic fan broadcast"}


def lang_fields(inst: InstanceSettings) -> dict:
    if inst.language == "ar":
        return {"language_name": "Arabic", "dialect": " (Modern Standard Arabic / فصحى, in the style of classic Arab football commentary — no dialect)"}
    return {"language_name": "English", "dialect": " (British football commentary)"}


def settings_key(inst: InstanceSettings) -> list:
    return [inst.language, inst.audience, inst.energy, inst.tone, inst.perspective, inst.focus_player_id]


def required_numbers(card: Card) -> list[str]:
    out = []
    for c in card.claims:
        try:
            v = float(str(c.value).rstrip("%"))
        except ValueError:
            continue
        out.append(str(int(v)) if v.is_integer() else f"{v:g}")
    return out


def numbers_ok(line: str, nums: list[str]) -> bool:
    found = set(re.findall(r"\d+(?:\.\d+)?", line.translate(AR_DIGITS)))
    return all(n in found for n in nums)


async def narrate(rt: "AgentRuntime", card: Card) -> str | None:
    """Returns the spoken line, or None (AR fallback = skip)."""
    inst = rt.booth.state.instance
    d = rt.booth.data
    system = prompts.NARRATOR.format(
        **lang_fields(inst), audience=inst.audience, audience_hint=AUDIENCE_HINT[inst.audience], energy=inst.energy,
        tone=inst.tone, perspective=PERSPECTIVE[inst.perspective],
        focus=d.name(inst.focus_player_id) if inst.focus_player_id else "none")
    nums = required_numbers(card)
    user = json.dumps({"card": card.text, "numbers_to_keep": nums}, ensure_ascii=False)
    for attempt in (0, 1):
        try:
            out = llm.parse_json(await llm.complete("narrator", "mini", system, user, timeout=15, effort="low",
                                                    cache_parts=[card.text, settings_key(inst), attempt]))
            line = str((out or {}).get("line") or "").strip()
        except (llm.LLMUnavailable, ValueError):
            break
        if line and numbers_ok(line, nums):
            return line
        await rt.booth.trace("narrator", "retry" if attempt == 0 else "fallback",
                             f"{card.id}: number check failed ({', '.join(nums)})")
    return card.text if inst.language == "en" else None


async def speak(rt: "AgentRuntime", text: str, inst: InstanceSettings, agent: str,
                excited: bool = False) -> tuple[str | None, int]:
    """TTS when AI voice is on; returns (audio_url, duration_ms). Failure → subtitle-only (§12.5)."""
    if inst.ai_voice:
        res = await llm.synthesize(text, inst.language, inst.energy, agent=f"tts_{agent}", excited=excited)
        if res:
            return f"/api/audio/{res[0]}.mp3", res[1]
    return None, llm.estimate_duration_ms(text, inst.language, inst.energy)
