"""Environment configuration (spec §4)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
REPO_DIR = BACKEND_DIR.parent
DATA_DIR = APP_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
STATIC_DIR = APP_DIR / "static"  # built frontend (Dockerfile copies frontend/dist here)

load_dotenv(REPO_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


AZURE_OPENAI_ENDPOINT = _env("FOUNDRY_ENDPOINT") or _env("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = _env("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = _env("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
MODEL_MINI = _env("MODEL_MINI", "gpt-5-mini")
MODEL_NANO = _env("MODEL_NANO", "gpt-5-nano")
SPEECH_KEY = _env("SPEECH_KEY")
SPEECH_REGION = _env("SPEECH_REGION")
VOICE_EN = _env("VOICE_EN", "en-GB-Harry:MAI-Voice-2.1")
VOICE_ES = _env("VOICE_ES", "es-MX-Alejo:MAI-Voice-2.1")
VOICE_FR = _env("VOICE_FR", "fr-FR-Marc:MAI-Voice-2.1")
VOICE_DE = _env("VOICE_DE", "de-DE-Klaus:MAI-Voice-2.1")
LANGUAGES = ("en", "es", "fr", "de")
CACHE_MODE = _env("CACHE_MODE", "off").lower()  # off | record | replay
MAX_LLM_CALLS_PER_MIN = int(_env("MAX_LLM_CALLS_PER_MIN", "40") or 40)
COST_CAP_USD = float(_env("COST_CAP_USD", "8") or 8)
DISPLAY_DELAY_S = 2.0

# USD per 1M tokens (input, output) — CLAUDE.md cost guard.
PRICES = {"mini": (0.275, 2.20), "nano": (0.05, 0.40)}
TTS_USD_PER_M_CHARS = 15.0

LLM_ENABLED = bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY)
TTS_ENABLED = bool(SPEECH_KEY and SPEECH_REGION)
