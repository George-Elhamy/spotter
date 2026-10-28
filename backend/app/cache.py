"""Record/replay cache for LLM responses and audio (spec §13)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import config

LLM_DIR = config.CACHE_DIR / "llm"
AUDIO_DIR = config.CACHE_DIR / "audio"


def make_key(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def get_llm(key: str) -> Any | None:
    if config.CACHE_MODE != "replay":
        return None
    path = LLM_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())["value"]
    return None


def put_llm(key: str, value: Any, meta: dict | None = None) -> None:
    if config.CACHE_MODE != "record":
        return
    LLM_DIR.mkdir(parents=True, exist_ok=True)
    (LLM_DIR / f"{key}.json").write_text(json.dumps({"value": value, "meta": meta or {}}, ensure_ascii=False))


def audio_path(audio_id: str):
    return AUDIO_DIR / f"{audio_id}.mp3"


def has_audio(audio_id: str) -> bool:
    return audio_path(audio_id).exists()


def put_audio(audio_id: str, data: bytes) -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_path(audio_id).write_bytes(data)
