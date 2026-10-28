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
FLOW_GROUP_S = 3.2  # a flowing call narrates the next few seconds of play in one line
FLOW = {"pass", "carry", "dribble", "duel", "tackle", "interception", "clearance", "block", "throw_in",
        "goal_kick", "free_kick", "corner", "offside", "foul"}
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
           "goal_line_clearance": "Cleared off the line by {player}!", "pass": "{player}, finds {related}.",
           "carry": "{player} carries it forward.", "tackle": "Good tackle from {player}.",
           "interception": "Intercepted by {player}.", "clearance": "{player} clears it.",
           "throw_in": "Throw-in, {team}.", "goal_kick": "Goal kick.", "free_kick": "Free kick to {team}.",
           "duel": "{player} battling with {related}.", "offside": "Flag's up, offside.", "block": "Blocked by {player}!"},
}


INTRO_FALLBACK = {
    "es": "¡Bienvenidos a {stadium}! {home} contra {away}, ¡empieza el espectáculo!",
    "fr": "Bienvenue à {stadium} ! {home} face à {away}, c'est parti !",
    "de": "Willkommen in {stadium}! {home} gegen {away} – los geht's!",
}


def _load_templates() -> dict:
    out = {}
    for lang in config.LANGUAGES:
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
    return t if t in BUILTIN["en"] else None


class Caller:
    def __init__(self, rt: "AgentRuntime") -> None:
        self.rt = rt
        self.templates = _load_templates()
        self.consumed: set[int] = set()
        self.last_minor_t = -999.0
        self.reserved_until = 0.0  # display-time the line being generated is expected to occupy
        self.backlog: list[dict] = []  # flow events that arrived while the channel was busy
        self.rng = random.Random(42)

    def reset(self) -> None:
        self.consumed.clear()
        self.last_minor_t = -999.0
        self.reserved_until = 0.0
        self.backlog = []

    def channel_free(self, t: float) -> bool:
        """True when nothing is scheduled or being generated on the shared speech channel at display-time t."""
        return max(self.rt.producer.speaking_until, self.reserved_until) <= t + 0.3

    def _speakable(self, e: dict) -> bool:
        t = e["type"]
        if self.rt.booth.clock.speed >= 5:
            return t in FAST_ONLY
        if t in HIGH or (t == "clearance" and e.get("subtype") == "goal_line"):
            return True
        # Continuous play-by-play: call the flow whenever the channel is free, unless the Producer
        # is waiting to air a card (the analyst gets the next gap).
        return t in FLOW and self.channel_free(e["t"]) and not self.rt.producer.wants_slot()

    def _group(self, e: dict) -> list[dict]:
        """Phase of play: this event plus speakable follow-ups within GROUP_S (shot → save/goal, foul → card...)."""
        evs = self.rt.booth.data.events
        group = [e]
        flow = e["type"] in FLOW
        i = e["id"]  # event ids are 1-based and sequential: events[e.id] is the next event
        while i < len(evs) and evs[i]["t"] <= e["t"] + (FLOW_GROUP_S if flow else GROUP_S):
            n = evs[i]
            if n["type"] in HIGH or n["type"] == "clearance" or (flow and n["type"] in FLOW):
                group.append(n)
                self.consumed.add(n["id"])
            if flow and n["type"] in HIGH:
                break
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
        tpl = self.rng.choice(variants) if variants else BUILTIN.get(lang, BUILTIN["en"]).get(key)
        if not tpl:
            return None
        st = self.rt.booth.state
        fields = defaultdict(str, player=d.name(e.get("player_id")), related=d.name(e.get("related_player_id")),
                             team=TEAM.get(e.get("team_id") or "", ""), score=f"{st.score[0]}-{st.score[1]}",
                             minute=str(e["minute"]))
        fields["opponent"] = TEAM["WHI" if e.get("team_id") == "RED" else "RED"]
        return tpl.format_map(fields)

    async def on_event(self, e: dict) -> None:
        if e["id"] in self.consumed:
            return
        if not self._speakable(e):
            if e["type"] in FLOW:
                self.backlog = (self.backlog + [e])[-8:]
            return
        self._start(e)

    async def intro(self) -> None:
        """Opening line when play starts (kickoff or rejoining after a jump) so the broadcast never starts silent."""
        rt, st = self.rt, self.rt.booth.state
        d, inst = rt.booth.data, st.instance
        table = {r["team_id"]: r for r in d.history.get("table", [])}
        facts = {
            "stadium": d.teams["RED"].get("stadium"), "home": d.teams["RED"]["name"], "away": d.teams["WHI"]["name"],
            "managers": [d.teams["RED"].get("manager"), d.teams["WHI"].get("manager")],
            "minute": st.match_time_label(), "kickoff": st.t < 5, "score": f"{st.score[0]}-{st.score[1]}",
            "league": {tid: {"position": table.get(tid, {}).get("position"), "points": table.get(tid, {}).get("pts")}
                       for tid in ("RED", "WHI")},
            "head_to_head_last3": d.history.get("head_to_head", [])[-3:],
        }
        line = subtitle = None
        try:
            system = prompts.OPENER.format(**lang_fields(inst), energy=inst.energy, tone=inst.tone,
                                           perspective=PERSPECTIVE[inst.perspective])
            out = llm.parse_json(await llm.complete("caller", "nano", system, json.dumps(facts, ensure_ascii=False),
                                                    timeout=6, cache_parts=["intro", facts["minute"], facts["score"],
                                                                            inst.language, inst.energy, inst.perspective]))
            line = str((out or {}).get("line") or "").strip() or None
            subtitle = str((out or {}).get("en") or "").strip() or None
        except (llm.LLMUnavailable, ValueError):
            pass
        if not line:
            en = (f"Welcome to {facts['stadium']}: {facts['home']} against {facts['away']}, and we're under way!"
                  if facts["kickoff"] else
                  f"Back with you at {facts['stadium']}, {facts['minute']} played, {facts['home']} {facts['score']} {facts['away']}.")
            local = INTRO_FALLBACK.get(inst.language)
            line, subtitle = (local.format(**facts), en) if local else (en, None)
        audio_url, dur = await speak(rt, line, inst, "caller", excited=inst.energy >= 4)
        play_at = rt.producer.display_now() + 0.3
        self.reserved_until = play_at + dur / 1000 * max(1.0, rt.booth.clock.speed)
        st.spoken = (st.spoken + [line])[-10:]
        await rt.producer.emit_speech("call", None, line, subtitle if inst.language != "en" else None, audio_url,
                                      play_at, dur, agent="caller")

    async def tick(self) -> None:
        """Fill gaps: as the current line is about to end, call the next stretch of play from the backlog."""
        if self.rt.booth.clock.speed >= 5 or self.rt.producer.wants_slot():
            return
        disp = self.rt.producer.display_now()
        if not self.channel_free(disp + 2.6):  # start generating ~2 s before the current line ends
            return
        ahead = max(disp + 0.4, self.rt.producer.speaking_until - 1.0)
        for e in self.backlog:
            if e["id"] not in self.consumed and e["t"] >= ahead:
                self.backlog = [b for b in self.backlog if b["t"] > e["t"]]
                self._start(e)
                return

    def _start(self, e: dict) -> None:
        group = self._group(e)
        main = self._main(group)
        span = max(2.4, group[-1]["t"] - group[0]["t"]) * max(1.0, self.rt.booth.clock.speed)
        self.reserved_until = max(self.reserved_until, e["t"] + span)
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
            subtitle = self.template_line(main, "en", inst.energy) if inst.language != "en" else None
        excited = main["type"] in ("goal", "save", "penalty_taken", "var_decision") or \
            (main["type"] == "shot" and main.get("outcome") in ("goal", "post", "saved"))
        audio_url, dur = await speak(rt, line, inst, "caller", excited=excited)
        st.spoken = (st.spoken + [line])[-10:]
        play_at = main["t"] if main["type"] != "goal" else group[0]["t"]
        if main["type"] in FLOW:  # flowing calls may start up to 1 s early to close gaps (still in sync)
            play_at = max(group[0]["t"] - 1.0, rt.producer.speaking_until + 0.2, rt.producer.display_now() + 0.2)
        self.reserved_until = min(self.reserved_until, max(play_at, rt.producer.speaking_until))
        await rt.producer.emit_speech("call", None, line, subtitle if inst.language != "en" else None, audio_url, play_at, dur, agent="caller")
        if source == "template":
            await rt.booth.trace("caller", "template", f"{main['type']} after {time.monotonic() - started:.1f}s: {line}")
