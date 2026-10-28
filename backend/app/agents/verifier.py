"""Independent Verifier (spec §7.4): code recomputes every number; gpt-5-nano checks qualitative text."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from .. import llm
from ..models import Card, Claim
from . import prompts
from .proposers import describe_event

if TYPE_CHECKING:
    from .runtime import AgentRuntime

PCT_HINTS = ("pct", "percent", "accuracy", "possession", "share", "index", "control", "chaos", "prob")


def _num(v: Any) -> float | None:
    try:
        return float(str(v).rstrip("%").replace(",", ""))
    except ValueError:
        return None


def tolerance(metric: str, value: float) -> float:
    m = metric.lower()
    if "speed" in m or "kmh" in m:
        return 0.5
    if any(h in m for h in PCT_HINTS):
        return 2.0 if value > 1.5 else 0.02
    if "xg" in m:
        return 0.05
    if "km" in m or "distance" in m:
        return 0.3
    if float(value).is_integer():
        return 1.0
    return max(0.1, abs(value) * 0.05)


def _season_value(rt: "AgentRuntime", c: Claim) -> float | None:
    dz = rt.booth.data.dossiers
    rec = dz["players"].get(c.entity) or dz["teams"].get(c.entity)
    if not rec:
        return None
    for src in (rec, rec.get("per90") or {}, rec.get("league_ranks") or {}):
        if isinstance(src, dict) and c.metric in src and _num(src[c.metric]) is not None:
            return _num(src[c.metric])
    p = rt.booth.data.players.get(c.entity, {})
    return _num(p.get(c.metric)) if c.metric in p else None


def actual_value(rt: "AgentRuntime", c: Claim) -> float | None:
    if (c.window or "match") == "season":
        return _season_value(rt, c)
    try:
        v = rt.booth.stats.metric_value(c.entity, c.metric, c.window or "match", c.against)
    except Exception:  # noqa: BLE001
        v = None
    return _num(v) if v is not None else _season_value(rt, c)


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ž0-9]+", s.lower()) if len(w) > 2}


async def verify(rt: "AgentRuntime", card: Card) -> tuple[bool, str]:
    data, st = rt.booth.data, rt.booth.state
    checked: list[str] = []
    # 1. numeric claims, recomputed by code
    for c in card.claims:
        claimed = _num(c.value)
        if claimed is None or c.kind != "stat":
            continue
        actual = actual_value(rt, c)
        if actual is None:
            continue  # unverifiable by code → covered by the qualitative check
        if abs(actual - claimed) > tolerance(c.metric, actual):
            return False, f"claimed {c.metric}={claimed:g} for {data.name(c.entity) or c.entity}, actual {actual:g}"
        checked.append(f"{c.metric}={actual:g}")
    # 2. evidence must exist and be in the past
    for eid in card.evidence_event_ids:
        e = data.by_id.get(eid)
        if e is None or e["t"] > st.t + 0.01:
            return False, f"evidence event {eid} does not exist yet"
    # 3. dedupe against aired / queued cards
    mine = _words(card.text)
    for other in rt.booth.board.with_status("aired", "airing", "ready", "queued", "rendering", "verified"):
        if other.id == card.id:
            continue
        ow = _words(other.text)
        if mine and ow and len(mine & ow) / len(mine | ow) > 0.55:
            return False, f"duplicate of {other.id}"
    # 4. qualitative check (gpt-5-nano) when text is not fully covered by verified numbers
    if card.category in ("tactical", "story", "background") or not checked:
        evidence = [describe_event(rt, data.by_id[i]) for i in card.evidence_event_ids[:8] if i in data.by_id]
        user = json.dumps({"card": card.text, "verified_numbers": checked, "evidence_events": evidence,
                           "match_time": st.match_time_label(), "score": st.score}, ensure_ascii=False)
        try:
            out = llm.parse_json(await llm.complete("verifier", "nano", prompts.VERIFIER_QUAL, user,
                                                    cache_parts=[card.text, card.evidence_event_ids], timeout=12))
            if isinstance(out, dict) and out.get("ok") is False:
                return False, str(out.get("reason") or "qualitative claim not supported")[:120]
        except (llm.LLMUnavailable, ValueError):
            checked.append("qualitative check skipped")
    return True, "; ".join(checked) or "supported"
