"""The ONLY module that talks to models or speech (CLAUDE.md cost guard, spec §0.1, §12, §13).

- Every LLM call reads token usage and adds cost to backend/app/data/cost_ledger.json.
- Every TTS call adds characters × $15/M.
- When the ledger reaches COST_CAP_USD all calls stop (raise CapReached) and listeners are notified
  so the UI shows a "cost cap reached" badge; callers fall back to templates / subtitles.
- MAX_LLM_CALLS_PER_MIN rate guard; 429 → one retry with backoff, then LLMUnavailable.
- CACHE_MODE record/replay for LLM outputs; audio is always cached by content hash.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from collections import deque
from typing import Any, Callable, Literal, Sequence
from xml.sax.saxutils import escape

from . import cache, config

log = logging.getLogger("spotter.llm")
Kind = Literal["mini", "nano"]
LEDGER_PATH = config.DATA_DIR / "cost_ledger.json"


class LLMUnavailable(Exception):
    """No LLM result: disabled, cap reached, rate limited, timed out or failed. Caller must fall back."""


class CapReached(LLMUnavailable):
    pass


# ---------------------------------------------------------------- cost ledger
class Ledger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {"total_usd": 0.0, "llm_calls": 0, "tts_chars": 0, "by_agent": {}}
        if LEDGER_PATH.exists():
            try:
                self.data.update(json.loads(LEDGER_PATH.read_text()))
            except (ValueError, OSError):
                log.warning("cost ledger unreadable; starting from 0")
        self._listeners: list[Callable[[], None]] = []
        self._announced = False

    @property
    def total(self) -> float:
        return float(self.data["total_usd"])

    @property
    def cap_reached(self) -> bool:
        return self.total >= config.COST_CAP_USD

    def on_cap(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def add(self, agent: str, usd: float, *, tokens_in: int = 0, tokens_out: int = 0, tts_chars: int = 0) -> None:
        with self._lock:
            d = self.data
            d["total_usd"] = round(d["total_usd"] + usd, 6)
            if tts_chars:
                d["tts_chars"] += tts_chars
            else:
                d["llm_calls"] += 1
            a = d["by_agent"].setdefault(agent, {"usd": 0.0, "calls": 0, "in": 0, "out": 0})
            a["usd"] = round(a["usd"] + usd, 6)
            a["calls"] += 1
            a["in"] += tokens_in
            a["out"] += tokens_out
            LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            LEDGER_PATH.write_text(json.dumps(d, indent=1))
        if self.cap_reached and not self._announced:
            self._announced = True
            log.error("COST CAP REACHED: $%.4f >= $%.2f — all LLM/TTS calls stopped", self.total, config.COST_CAP_USD)
            for fn in self._listeners:
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    log.exception("cap listener failed")

    def check(self) -> None:
        if self.cap_reached:
            raise CapReached(f"cost cap ${config.COST_CAP_USD} reached")


ledger = Ledger()


def llm_cost(kind: Kind, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = config.PRICES[kind]
    return tokens_in / 1e6 * p_in + tokens_out / 1e6 * p_out


# ---------------------------------------------------------------- rate guard
_calls: deque[float] = deque()


def _rate_ok() -> bool:
    now = time.monotonic()
    while _calls and now - _calls[0] > 60:
        _calls.popleft()
    if len(_calls) >= config.MAX_LLM_CALLS_PER_MIN:
        return False
    _calls.append(now)
    return True


degraded_until = 0.0  # set after a hard 429; Producer degrades to code-only ranking (§12.6)


def is_degraded() -> bool:
    return time.monotonic() < degraded_until


# ---------------------------------------------------------------- clients
_clients: dict[Kind, Any] = {}


def _client(kind: Kind):
    if kind not in _clients:
        from agent_framework.openai import OpenAIChatCompletionClient

        _clients[kind] = OpenAIChatCompletionClient(
            model=config.MODEL_MINI if kind == "mini" else config.MODEL_NANO,
            azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
            api_key=config.AZURE_OPENAI_API_KEY,
            api_version=config.AZURE_OPENAI_API_VERSION,
        )
    return _clients[kind]


def _usage(resp: Any) -> tuple[int, int]:
    u = getattr(resp, "usage_details", None) or {}
    get = u.get if isinstance(u, dict) else (lambda k, d=None: getattr(u, k, d))
    return int(get("input_token_count", 0) or 0), int(get("output_token_count", 0) or 0)


def _is_rate_limit(e: Exception) -> bool:
    s = f"{type(e).__name__} {e}"
    return "429" in s or "RateLimit" in s or "rate limit" in s.lower()


def parse_json(text: str) -> Any:
    """Parse model JSON output; tolerates code fences and leading prose. 'null' → None."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r"(\{.*\}|\[.*\])", t, re.S)
        if m:
            return json.loads(m.group(1))
        if t.lower() in ("null", "none", ""):
            return None
        raise


async def _guarded(agent: str, kind: Kind, cache_parts: Sequence[Any] | None, timeout: float,
                   call: Callable[[], Any]) -> str:
    """Shared path: cache → cap → rate → call with timeout and one 429 retry → ledger → cache."""
    global degraded_until
    key = cache.make_key(agent, kind, *cache_parts) if cache_parts is not None else None
    if key:
        hit = cache.get_llm(key)
        if hit is not None:
            return hit
    if not config.LLM_ENABLED:
        raise LLMUnavailable("LLM not configured")
    ledger.check()
    if not _rate_ok():
        raise LLMUnavailable("MAX_LLM_CALLS_PER_MIN reached")
    for attempt in (0, 1):
        try:
            resp = await asyncio.wait_for(call(), timeout=timeout)
            break
        except asyncio.TimeoutError as e:
            raise LLMUnavailable(f"{agent} timed out after {timeout}s") from e
        except Exception as e:  # noqa: BLE001
            if _is_rate_limit(e) and attempt == 0:
                await asyncio.sleep(2.0)
                continue
            if _is_rate_limit(e):
                degraded_until = time.monotonic() + 30
            raise LLMUnavailable(f"{agent}: {type(e).__name__}: {str(e)[:200]}") from e
    t_in, t_out = _usage(resp)
    ledger.add(agent, llm_cost(kind, t_in, t_out), tokens_in=t_in, tokens_out=t_out)
    text = resp.text or ""
    if key:
        cache.put_llm(key, text, {"agent": agent, "in": t_in, "out": t_out})
    return text


async def complete(agent: str, kind: Kind, system: str, user: str, *, cache_parts: Sequence[Any] | None = None,
                   timeout: float = 20.0, json_mode: bool = True, effort: str = "minimal") -> str:
    """Single-turn chat completion (Verifier, Producer fit, Narrator, Caller, directive parser)."""
    from agent_framework import Message

    options: dict[str, Any] = {"reasoning_effort": effort}
    if json_mode:
        options["response_format"] = {"type": "json_object"}
    msgs = [Message("system", [system]), Message("user", [user])]
    # cache_parts must be deterministic for a given moment + settings (not the full prompt, which embeds
    # timing-dependent board content) so CACHE_MODE=replay hits on re-runs.
    return await _guarded(agent, kind, cache_parts, timeout, lambda: _client(kind).get_response(msgs, options=options))


async def run_agent(agent: str, instructions: str, tools: Sequence[Any], prompt: str, *, kind: Kind = "mini",
                    cache_parts: Sequence[Any] | None = None, timeout: float = 45.0, effort: str = "low") -> str:
    """Run a Microsoft Agent Framework agent with function tools (proposers)."""
    from agent_framework import Agent

    af_agent = Agent(_client(kind), instructions, name=agent, tools=list(tools),
                     default_options={"reasoning_effort": effort, "response_format": {"type": "json_object"}})
    return await _guarded(agent, kind, cache_parts, timeout, lambda: af_agent.run(prompt))


# ---------------------------------------------------------------- TTS
# energy 1 calm → 5 hype: (rate, pitch, volume)
ENERGY_PROSODY = {1: ("-10%", "-5%", "medium"), 2: ("-4%", "-2%", "medium"), 3: ("+3%", "+2%", "default"),
                  4: ("+12%", "+8%", "loud"), 5: ("+22%", "+15%", "x-loud")}
# expressive styles for MAI voices (energy ≥ 4, or "excited" moments like goals at energy ≥ 3)
MAI_STYLE = {"calm": None, "lively": "joyful", "excited": "surprised"}
_speech_lock = asyncio.Lock()


def voice_for(language: str) -> str:
    return {"es": config.VOICE_ES, "fr": config.VOICE_FR, "de": config.VOICE_DE}.get(language, config.VOICE_EN)


def is_hd(voice: str) -> bool:
    return ":MAI-Voice" in voice and not voice.endswith("-Flash") or "HD" in voice


def build_ssml(text: str, language: str, energy: int, excited: bool = False) -> str:
    voice = voice_for(language)
    lang = "-".join(voice.split("-")[:2])
    energy = int(energy) if int(energy) in ENERGY_PROSODY else 3
    rate, pitch, volume = ENERGY_PROSODY[energy]
    body = escape(text)
    if ":MAI-Voice" in voice:
        mood = "excited" if excited and energy >= 3 else ("lively" if energy >= 4 else "calm")
        style = MAI_STYLE[mood]
        if style == "surprised" and not voice.startswith("en-"):
            style = "excited"
        if style:
            body = f'<mstts:express-as style="{style}">{body}</mstts:express-as>'
    else:
        if excited and energy >= 3:  # big moments get an extra lift on standard voices
            rate, pitch, volume = ENERGY_PROSODY[min(5, energy + 1)]
        body = f'<prosody rate="{rate}" pitch="{pitch}" volume="{volume}">{body}</prosody>'
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{lang}">'
            f'<voice name="{voice}">{body}</voice></speak>')


def estimate_duration_ms(text: str, language: str, energy: int = 3) -> int:
    wps = (2.6 if language == "en" else 2.2) * (1 + (int(energy) - 3) * 0.05)
    return int(max(1.0, len(text.split()) / wps) * 1000) + 250


async def synthesize(text: str, language: str, energy: int, *, agent: str = "tts",
                     excited: bool = False) -> tuple[str, int] | None:
    """Returns (audio_id, duration_ms) or None (→ subtitle-only, §12.5). Audio served at /api/audio/{id}.mp3."""
    ssml = build_ssml(text, language, energy, excited)
    audio_id = cache.make_key("tts", ssml)
    meta_path = cache.AUDIO_DIR / f"{audio_id}.json"
    if cache.has_audio(audio_id) and meta_path.exists():
        return audio_id, json.loads(meta_path.read_text())["duration_ms"]
    if not config.TTS_ENABLED or ledger.cap_reached:
        return None

    def _run() -> tuple[bytes, int] | None:
        import azure.cognitiveservices.speech as speechsdk

        cfg = speechsdk.SpeechConfig(subscription=config.SPEECH_KEY, region=config.SPEECH_REGION)
        cfg.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3)
        synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
        res = synth.speak_ssml_async(ssml).get()
        if res.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            detail = getattr(res, "cancellation_details", None)
            log.warning("TTS failed: %s %s", res.reason, getattr(detail, "error_details", ""))
            return None
        return bytes(res.audio_data), int(res.audio_duration.total_seconds() * 1000)

    try:
        out = await asyncio.wait_for(asyncio.to_thread(_run), timeout=10)
    except Exception as e:  # noqa: BLE001
        log.warning("TTS error: %s", e)
        return None
    if out is None:
        return None
    data, dur = out
    # HD/MAI voices are billed above standard neural; count them at 2× to stay conservative.
    price = config.TTS_USD_PER_M_CHARS * (2 if is_hd(voice_for(language)) else 1)
    ledger.add(agent, len(ssml) / 1e6 * price, tts_chars=len(ssml))
    cache.put_audio(audio_id, data)
    meta_path.write_text(json.dumps({"duration_ms": dur, "text": text}))
    return audio_id, dur
