"""Caller — play-by-play (spec §7.7): phases of play inside the 2 s lookahead; 1.4 s deadline → template."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections import defaultdict
from typing import TYPE_CHECKING

from .. import config, llm
from . import prompts
from .narrator import PERSPECTIVE, lang_fields, speak

if TYPE_CHECKING:
    from .runtime import AgentRuntime

log = logging.getLogger("spotter.caller")
DEADLINE_S = 1.4
GROUP_S = 2.0
HIGH = {"goal", "shot", "save", "penalty_awarded", "penalty_taken", "card", "var_check", "var_decision", "half_time",
        "full_time", "kickoff", "substitution", "injury"}
FAST_ONLY = {"goal", "shot", "card", "penalty_taken"}
RANK = ["goal", "penalty_taken", "save", "shot", "card", "var_decision", "var_check", "penalty_awarded"]
TEAM = {"RED": "Redmoor", "WHI": "Whitcliffe"}

# Minimal built-in fallback; scripts/make_templates.py generates the full committed set.
BUILTIN = {
    "en": {"goal": "GOAL! {player} scores for {team}!", "shot_saved": "{player} shoots — saved!",
           "shot_off_target": "{player} fires wide.", "shot_blocked": "{player}'s shot is blocked.",
           "shot_post": "{player} hits the post!", "save": "Good save.", "card_yellow": "Yellow card for {player}.",
           "card_red": "{player} is sent off!", "foul": "Foul by {player}.", "corner": "Corner to {team}.",
           "penalty_awarded": "Penalty to {team}!", "penalty_saved": "Saved! The penalty is saved!",
           "penalty_scored": "{player} converts the penalty!", "var_check": "VAR is checking this one.",
           "var_decision": "VAR decision: the goal is ruled out!", "substitution": "{player} comes on for {related}.",
           "injury": "{player} is down injured.", "kickoff": "We're under way.", "half_time": "Half-time.",
           "full_time": "Full-time!", "attack": "{team} on the attack.", "dribble": "{player} skips past {related}.",
           "goal_line_clearance": "Cleared off the line by {player}!"},
    "ar": {"goal": "هدف! {player} يسجل لـ{team}!", "shot_saved": "تسديدة من {player}… والحارس يتصدى!",
           "shot_off_target": "تسديدة {player} تمر بجوار المرمى.", "shot_blocked": "تسديدة {player} تُصد.",
           "shot_post": "القائم! كرة {player} ترتطم بالقائم!", "save": "تصدٍّ رائع من الحارس!",
           "card_yellow": "بطاقة صفراء لـ{player}.", "card_red": "بطاقة حمراء! {player} يغادر الملعب!",
           "foul": "خطأ على {player}.", "corner": "ركلة ركنية لـ{team}.", "penalty_awarded": "ركلة جزاء لـ{team}!",
           "penalty_saved": "تصدى لها! الحارس يصد ركلة الجزاء!", "penalty_scored": "{player} يسجل من ركلة الجزاء!",
           "var_check": "حكم الفيديو يراجع اللقطة.", "var_decision": "حكم الفيديو يلغي الهدف!",
           "substitution": "{player} يدخل بدلاً من {related}.", "injury": "{player} سقط مصاباً.",
           "kickoff": "انطلقت المباراة.", "half_time": "نهاية الشوط الأول.", "full_time": "نهاية المباراة!",
           "attack": "هجمة لـ{team}.", "dribble": "{player} يراوغ {related}!",
           "goal_line_clearance": "{player} يبعدها من على خط المرمى!"},
}


def _load_templates() -> dict:
    out = {}
    for lang in ("en", "ar"):
        p = config.DATA_DIR / f"templates_{lang}.json"
        try:
            out[lang] = json.loads(p.read_text()) if p.exists() else {}
        except ValueError:
            out[lang] = {}
    return out


def event_key(e: dict) -> str | None:
    t, o = e["type"], e.get("outcome")
    if t == "shot":
        return {"saved": "shot_saved", "off_target": "shot_off_target", "blocked": "shot_blocked", "post": "shot_post",
                "goal": "goal"}.get(o or "", "shot_off_target")
    if t == "card":
        return "card_yellow" if e.get("card") == "yellow" else "card_red"
    if t == "penalty_taken":
        return "penalty_scored" if o == "goal" else "penalty_saved"
    if t == "clearance" and e.get("subtype") == "goal_line":
        return "goal_line_clearance"
    if t == "dribble":
        return "dribble"
    if t == "pass":
        return "attack"
    return t if t in BUILTIN["en"] else None


class Caller:
    def __init__(self, rt: "AgentRuntime") -> None:
        self.rt = rt
        self.templates = _load_templates()
        self.consumed: set[int] = set()
        self.last_minor_t = -999.0
        self.rng = random.Random(42)

    def reset(self) -> None:
        self.consumed.clear()
        self.last_minor_t = -999.0

    def _speakable(self, e: dict) -> bool:
        t = e["type"]
        if self.rt.booth.clock.speed >= 5:
            return t in FAST_ONLY
        if t in HIGH or (t == "clearance" and e.get("subtype") == "goal_line"):
            return True
        busy = self.rt.producer.speaking_until > e["t"] - 0.5
        if busy or e["t"] - self.last_minor_t < 10:
            return False
        if t in ("foul", "corner") or (t == "dribble" and e.get("outcome") in ("won", "complete")):
            return True
        if t == "pass" and e.get("outcome") == "complete" and e.get("end"):
            x = e["end"]["x"]
            attack_dir = self.rt.booth.data.meta["attack_direction"][str(e["period"])][e["team_id"]]
            in_box = (x > 88.5 if attack_dir == "+x" else x < 16.5) and 13.8 < e["end"]["y"] < 54.2
            return in_box
        return False

    def _group(self, e: dict) -> list[dict]:
        """Phase of play: this event plus speakable follow-ups within GROUP_S (shot → save/goal, foul → card...)."""
        evs = self.rt.booth.data.events
        st = self.rt.booth.state
        group = [e]
        i = st.next_idx
        while i < len(evs) and evs[i]["t"] <= e["t"] + GROUP_S:
            n = evs[i]
            if n["type"] in HIGH or n["type"] == "clearance":
                group.append(n)
                self.consumed.add(n["id"])
            i += 1
        return group

    def _main(self, group: list[dict]) -> dict:
        def rank(ev: dict) -> int:
            return RANK.index(ev["type"]) if ev["type"] in RANK else len(RANK)
        return min(group, key=rank)

    def template_line(self, e: dict, lang: str, energy: int) -> str | None:
        key = event_key(e)
        if not key:
            return None
        d = self.rt.booth.data
        bucket = "1" if energy <= 2 else ("3" if energy == 3 else "5")
        variants = (self.templates.get(lang, {}).get(key) or {}).get(bucket) or []
        tpl = self.rng.choice(variants) if variants else BUILTIN[lang].get(key)
        if not tpl:
            return None
        st = self.rt.booth.state
        fields = defaultdict(str, player=d.name(e.get("player_id")), related=d.name(e.get("related_player_id")),
                             team=TEAM.get(e.get("team_id") or "", ""), score=f"{st.score[0]}-{st.score[1]}",
                             minute=str(e["minute"]))
        fields["opponent"] = TEAM["WHI" if e.get("team_id") == "RED" else "RED"]
        return tpl.format_map(fields)

    async def on_event(self, e: dict) -> None:
        if e["id"] in self.consumed or not self._speakable(e):
            return
        group = self._group(e)
        main = self._main(group)
        if main["type"] not in HIGH:
            self.last_minor_t = e["t"]
        asyncio.create_task(self._call(group, main))

    async def _call(self, group: list[dict], main: dict) -> None:
        rt = self.rt
        st = rt.booth.state
        inst = st.instance
        from .proposers import describe_event

        started = time.monotonic()
        line, subtitle, source = None, None, "llm"
        if not llm.ledger.cap_reached:
            system = prompts.CALLER.format(**lang_fields(inst), energy=inst.energy, tone=inst.tone,
                                           perspective=PERSPECTIVE[inst.perspective],
                                           recent=json.dumps(st.spoken[-10:], ensure_ascii=False))
            user = "Events (in order): " + " | ".join(describe_event(rt, g) for g in group) + \
                   f"\nScore now: Redmoor {st.score[0]} – {st.score[1]} Whitcliffe."
            try:
                out = llm.parse_json(await llm.complete(
                    "caller", "nano", system, user, timeout=DEADLINE_S,
                    cache_parts=[[g["id"] for g in group], inst.language, inst.energy, inst.tone, inst.perspective]))
                line = str((out or {}).get("line") or "").strip() or None
                subtitle = str((out or {}).get("en") or "").strip() or None
            except (llm.LLMUnavailable, ValueError) as ex:
                log.info("caller fallback: %s", ex)
        if not line:
            source = "template"
            line = self.template_line(main, inst.language, inst.energy)
            if not line:
                return
            subtitle = self.template_line(main, "en", inst.energy) if inst.language == "ar" else None
        excited = main["type"] in ("goal", "save", "penalty_taken", "var_decision") or \
            (main["type"] == "shot" and main.get("outcome") in ("goal", "post", "saved"))
        audio_url, dur = await speak(rt, line, inst, "caller", excited=excited)
        st.spoken = (st.spoken + [line])[-10:]
        play_at = main["t"] if main["type"] != "goal" else group[0]["t"]
        await rt.producer.emit_speech("call", None, line, subtitle if inst.language == "ar" else None, audio_url, play_at, dur, agent="caller")
        if source == "template":
            await rt.booth.trace("caller", "template", f"{main['type']} after {time.monotonic() - started:.1f}s: {line}")
