"""Proposer agents (spec §7.3): Microsoft Agent Framework agents with function tools, writing cards to the board."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .. import llm
from ..models import Card, Claim
from . import prompts

if TYPE_CHECKING:
    from .runtime import AgentRuntime

log = logging.getLogger("spotter.proposers")


def describe_event(rt: "AgentRuntime", e: dict) -> str:
    d = rt.booth.data
    s = f"[{e['id']}] {rt.booth.state.match_time_label(e)} {e['type']}"
    if e.get("subtype"):
        s += f"/{e['subtype']}"
    team = {"RED": "Redmoor", "WHI": "Whitcliffe"}
    if e.get("player_id"):
        s += f" {d.name(e['player_id'])} ({e['player_id']}, {team.get(e.get('team_id') or '', '')})"
    if e.get("related_player_id"):
        rel = d.players.get(e["related_player_id"], {})
        s += f" → {d.name(e['related_player_id'])} ({e['related_player_id']}, {team.get(rel.get('team_id', ''), '')})"
    if e.get("outcome"):
        s += f" [{e['outcome']}]"
    if e.get("card"):
        s += f" card={e['card']}"
    return s


def system_prompt(rt: "AgentRuntime", agent: str) -> str:
    return prompts.PROPOSER_COMMON.format(**prompts.PROPOSERS[agent], metrics=", ".join(rt.metric_names))


def context_prompt(rt: "AgentRuntime", agent: str, trigger: dict) -> str:
    st = rt.booth.state
    d = rt.booth.data
    recent = d.events[max(0, st.next_idx - 6):st.next_idx]
    lines = [
        f"Match time {st.match_time_label()} (t={st.t:.0f}s), period {st.period}. "
        f"Score: Redmoor Rovers {st.score[0]} – {st.score[1]} Whitcliffe Athletic. "
        f"Players on pitch: RED {sum(1 for p in st.on_pitch if p.startswith('RED'))}, WHI {sum(1 for p in st.on_pitch if p.startswith('WHI'))}.",
        f"Why you were woken: {trigger['reason']}",
    ]
    if trigger.get("event"):
        lines.append("Trigger event: " + describe_event(rt, trigger["event"]))
    if trigger.get("alerts"):
        lines.append("New stats alerts: " + json.dumps(trigger["alerts"][:5], ensure_ascii=False))
    lines.append("Latest events: " + " | ".join(describe_event(rt, e) for e in recent))
    inst = st.instance
    if inst.focus_player_id:
        lines.append(f"Showrunner focus player: {d.name(inst.focus_player_id)} ({inst.focus_player_id}) — prefer insights about this player.")
    dirs = [f"{x.type}:{x.target}" for x in inst.directives]
    if dirs:
        lines.append("Active showrunner directives: " + ", ".join(dirs))
    return "\n".join(lines)


def _card_from_json(rt: "AgentRuntime", agent: str, obj: Any) -> Card | None:
    if not isinstance(obj, dict):
        return None
    c = obj.get("card", obj if "text" in obj else None)
    if not c or not isinstance(c, dict) or not c.get("text"):
        return None
    players = rt.booth.data.players
    claims = []
    for cl in c.get("claims") or []:
        try:
            claims.append(Claim(**{k: cl.get(k) for k in ("kind", "entity", "metric", "against", "window", "value")
                                   if cl.get(k) is not None}))
        except Exception:  # noqa: BLE001 — malformed claim → verifier will not see it; text check still applies
            log.info("dropping malformed claim %s", cl)
    category = prompts.PROPOSERS[agent]["category"]
    team = c.get("team_id") if c.get("team_id") in ("RED", "WHI") else None
    return Card(
        id=rt.booth.board.new_id(), agent=agent, created_t=round(rt.booth.state.t, 1), text=str(c["text"]).strip(),
        category=category, player_ids=[p for p in c.get("player_ids") or [] if p in players], team_id=team,
        claims=claims, evidence_event_ids=[int(i) for i in c.get("evidence_event_ids") or [] if str(i).isdigit()],
        priority=max(1, min(5, int(c.get("priority") or 3))), time_sensitive=bool(c.get("time_sensitive", True)),
        ttl_s=float(max(20, min(300, float(c.get("ttl_s") or (300 if category == "background" else 30))))),
    )


async def propose(rt: "AgentRuntime", agent: str, trigger: dict, revision: tuple[Card, str] | None = None) -> Card | None:
    prompt = context_prompt(rt, agent, trigger)
    if revision:
        card, reason = revision
        prompt += "\n\n" + prompts.REVISION.format(card=card.model_dump_json(include={"text", "claims"}), reason=reason)
    inst = rt.booth.state.instance
    cache_parts = [trigger["key"], revision[1] if revision else None, inst.focus_player_id,
                   sorted(f"{d.type}:{d.target}" for d in inst.directives)]
    text = await llm.run_agent(agent, system_prompt(rt, agent), rt.tools[agent], prompt, cache_parts=cache_parts)
    try:
        return _card_from_json(rt, agent, llm.parse_json(text))
    except ValueError:
        log.warning("%s returned non-JSON: %s", agent, text[:200])
        return None
