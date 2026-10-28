"""Generate play-by-play fallback templates (spec §5.1, §7.7) into app/data/templates_{en,ar}.json.

One gpt-5-mini call per (key, lang) through app.llm.complete — never a direct model call — returning
all three energy buckets at once (~46 calls, a few cents). Variants are validated (placeholders,
word limit, banned real-world names, duplicates) and the winners are committed.

Resumable: writes templates_{lang}.json after every key; keys already holding 6 valid variants per
bucket are skipped, partial keys are topped up.

Run from backend/:  .venv/bin/python -m scripts.make_templates
"""
from __future__ import annotations

import asyncio
import json
import sys
from string import Formatter
from typing import Any

from app import config, llm
from app.agents.caller import BUILTIN

BUCKETS = ("1", "3", "5")
ASK_PER_BUCKET = 8
KEEP = 6
MIN_VALID = 4
MAX_ATTEMPTS = 3
MAX_WORDS = {"goal": 25}
DEFAULT_MAX_WORDS = 15
KEYS = list(BUILTIN["en"])

STYLE = {
    "en": "British football television commentary — natural UK commentator vocabulary (pitch, keeper, the top corner, brilliant, lovely touch).",
    "ar": "classic Arab football commentary in Modern Standard Arabic (فصحى) — vivid, energetic, no dialect.",
}
EVENTS = {
    "goal": "a goal is scored",
    "shot_saved": "a shot is saved by the goalkeeper",
    "shot_off_target": "a shot goes wide of the goal",
    "shot_blocked": "a shot is blocked by a defender",
    "shot_post": "a shot hits the post",
    "save": "the goalkeeper makes a good save",
    "card_yellow": "the referee shows a yellow card",
    "card_red": "a red card — the player is sent off",
    "foul": "a foul is committed",
    "corner": "a corner kick is awarded",
    "penalty_awarded": "the referee awards a penalty",
    "penalty_saved": "a penalty is saved by the goalkeeper",
    "penalty_scored": "a penalty is scored",
    "var_check": "the video assistant referee (VAR) starts reviewing a decision",
    "var_decision": "the VAR review finishes and the goal is disallowed",
    "substitution": "a substitution",
    "injury": "a player is down injured",
    "kickoff": "kickoff — the match (re)starts",
    "half_time": "the half-time whistle",
    "full_time": "the full-time whistle",
    "attack": "a team builds an attack",
    "dribble": "a player takes on and beats an opponent one-v-one",
    "goal_line_clearance": "a defender clears the ball off the goal line",
}
KEY_NOTES = {
    "substitution": " {player} comes on, {related} goes off.",
    "dribble": " {player} is the dribbler, {related} is the beaten defender.",
}
BANNED = ("premier league", "champions league", "fa cup", "arsenal", "liverpool", "chelsea", "manchester",
          "man city", "tottenham", "everton", "newcastle", "real madrid", "barcelona", "juventus", "bayern",
          "dortmund", "psg", "messi", "ronaldo", "haaland", "salah", "mbappe", "klopp", "guardiola",
          "ليفربول", "أرسنال", "تشيلسي", "برشلونة", "ريال مدريد", "مانشستر", "بريميرليج")


def placeholders_in(line: str) -> list[str]:
    return [f for _, f, _, _ in Formatter().parse(line) if f]


def valid_variant(text: Any, key: str, allowed: list[str]) -> str | None:
    if not isinstance(text, str):
        return None
    t = text.strip().strip('"«»').strip()
    if not t:
        return None
    try:
        t.format_map({p: f"[{p}]" for p in allowed})
    except (KeyError, ValueError, IndexError):
        return None
    low = t.casefold()
    if any(b in low for b in BANNED):
        return None
    if len(t.split()) > MAX_WORDS.get(key, DEFAULT_MAX_WORDS):
        return None
    return t


def norm(line: str) -> str:
    return " ".join(line.split()).casefold()


def load_existing(lang: str) -> dict[str, dict[str, list[str]]]:
    path = config.DATA_DIR / f"templates_{lang}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {k: {b: [] for b in BUCKETS} for k in KEYS}
    out = {k: {b: [] for b in BUCKETS} for k in KEYS}
    if isinstance(data, dict):
        for k, v in data.items():
            if k in out and isinstance(v, dict):
                for b in BUCKETS:
                    if isinstance(v.get(b), list):
                        out[k][b] = [x for x in v[b] if isinstance(x, str)][:KEEP]
    return out


def write_file(lang: str, results: dict[str, dict[str, list[str]]]) -> None:
    path = config.DATA_DIR / f"templates_{lang}.json"
    payload = {key: results[key] for key in KEYS}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def system_prompt(lang: str) -> str:
    arabic = ("\n- Write every line in Modern Standard Arabic (فصحى), no dialect. Placeholders stay EXACTLY as given, Latin "
              "letters inside the braces ({player}, never a translated placeholder)." if lang == "ar" else "")
    return f"""You write fallback play-by-play lines for Spotter, an AI commentator covering a fully fictional
football league (Redmoor Rovers vs Whitcliffe Athletic — invented clubs only). Style: {STYLE[lang]}.

A template is ONE spoken commentary line. Placeholders in braces are filled at runtime:
{{player}} = the player involved · {{related}} = the other player (beaten defender / player going off) ·
{{team}} = the acting team · {{opponent}} = the other team · {{score}} = current score · {{minute}} = match minute.

Hard rules:
- Use ONLY the placeholders listed for the event, copying them character-for-character; never translate,
  rename or invent placeholders.{arabic}
- Western digits only (0-9), never Arabic-Indic digits.
- No real players, clubs, leagues or competitions — ever.
- No emojis, no quotes around lines, no stage directions — only the spoken line.
- Vary openings and rhythm; never repeat a variant.

Energy buckets: "1" = calm and measured, "3" = normal match commentary, "5" = full-hype big-moment roar.

Return JSON only, exactly this shape with {ASK_PER_BUCKET} lines per bucket, every line a plain string:
{{"1": [lines], "3": [lines], "5": [lines]}}"""


def user_prompt(key: str, lang: str, feedback: str) -> str:
    allowed = placeholders_in(BUILTIN["en"][key])
    ph = " ".join("{" + p + "}" for p in allowed) or "none — plain lines only"
    return f"""Event: {EVENTS[key]}.{KEY_NOTES.get(key, "")}
STRICT: the only permitted placeholders are {ph} (you may omit some). Any other placeholder —
especially {{"score"}}, {{"minute"}} or {{"opponent"}} if not listed — makes the line INVALID and it is discarded.
Max {MAX_WORDS.get(key, DEFAULT_MAX_WORDS)} words per line.

Write {ASK_PER_BUCKET} variants of this event for each energy bucket ({", ".join(BUCKETS)}).
Return JSON only: {{"1": [...], "3": [...], "5": [...]}}{feedback}"""


async def generate_key(lang: str, key: str, seed: dict[str, list[str]]) -> dict[str, list[str]]:
    out = {b: list(seed.get(b, []))[:KEEP] for b in BUCKETS}
    seen = {norm(t) for lines in out.values() for t in lines}
    feedback = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        cp = ("make_templates", lang, key) if attempt == 1 else None
        try:
            raw = await llm.complete("templates", "mini", system_prompt(lang), user_prompt(key, lang, feedback),
                                     timeout=45.0, cache_parts=cp)
        except llm.LLMUnavailable as e:
            print(f"  {lang}/{key} attempt {attempt}: {str(e)[:100]}", flush=True)
            await asyncio.sleep(15.0 if "MAX_LLM_CALLS_PER_MIN" in str(e) else 2.0)
            continue
        try:
            data = llm.parse_json(raw) or {}
        except ValueError:
            data = {}
        invalid = 0
        for b in BUCKETS:
            lines = data.get(b) if isinstance(data, dict) else None
            for line in lines if isinstance(lines, list) else []:
                t = valid_variant(line, key, placeholders_in(BUILTIN["en"][key]))
                n = norm(t) if t else ""
                if t is None or n in seen or len(out[b]) >= KEEP:
                    invalid += 1
                    continue
                seen.add(n)
                out[b].append(t)
        if min(len(v) for v in out.values()) >= MIN_VALID:
            break
        feedback = (f"\n\nYour previous output was partly unusable ({invalid} lines dropped: wrong placeholders, "
                     f"too many words, banned names, or duplicates). Write {ASK_PER_BUCKET} fresh variants per "
                     "bucket; do not repeat earlier lines.")
    return out


def say(msg: str) -> None:
    print(msg, flush=True)


async def main() -> int:
    if not config.LLM_ENABLED:
        say("LLM not configured: set AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY in .env")
        return 2
    before = llm.ledger.total
    results: dict[str, dict[str, dict[str, list[str]]]] = {}
    problems: list[str] = []
    i = 0
    for lang in ("en", "ar"):
        results[lang] = load_existing(lang)
        for key in KEYS:
            i += 1
            seed = results[lang][key]
            if all(len(seed[b]) >= KEEP for b in BUCKETS):
                say(f"[{i:02d}/{len(KEYS) * 2}] {lang} {key:22} skip (full)")
                continue
            buckets = await generate_key(lang, key, seed)
            results[lang][key] = buckets
            write_file(lang, results[lang])
            counts = "/".join(str(len(buckets[b])) for b in BUCKETS)
            say(f"[{i:02d}/{len(KEYS) * 2}] {lang} {key:22} {counts}  ${llm.ledger.total - before:.4f}")
            if min(len(v) for v in buckets.values()) < MIN_VALID:
                problems.append(f"{lang}/{key}: " + ", ".join(f"{b}={len(v)}" for b in BUCKETS))
            await asyncio.sleep(0.2)

    def count(lang_data: dict[str, dict[str, list[str]]]) -> int:
        return sum(len(lines) for buckets in lang_data.values() for lines in buckets.values())

    total = sum(count(results[lang]) for lang in ("en", "ar"))
    for lang in ("en", "ar"):
        say(f"wrote {config.DATA_DIR / f'templates_{lang}.json'} ({count(results[lang])} lines)")
    say(f"templates total: {total} lines across {len(KEYS)} keys x 2 languages (6 per key per bucket)")
    say(f"run cost ${llm.ledger.total - before:.4f}; ledger total ${llm.ledger.total:.4f} "
        f"(cap ${config.COST_CAP_USD}, cache_mode={config.CACHE_MODE})")
    if problems:
        say("SHORT BUCKETS (need >= 4): " + "; ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
