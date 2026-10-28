"""Shared API contract (spec §5.6, §7.1, §9, §10). Mirror of frontend/src/types/contract.ts."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

TeamId = Literal["RED", "WHI"]
AgentName = Literal["stats_scout", "tactical", "dossier", "storyline"]
AGENTS: tuple[str, ...] = ("stats_scout", "tactical", "dossier", "storyline")
CardStatus = Literal[
    "proposed", "verifying", "rejected", "revising", "verified", "skipped", "queued",
    "rendering", "ready", "airing", "aired", "expired", "removed", "discarded",
]
TERMINAL_STATUSES = {"skipped", "aired", "expired", "removed", "discarded"}


class Claim(BaseModel):
    kind: str = "stat"
    entity: str
    metric: str
    against: Optional[str] = None
    window: Optional[str] = None
    value: float | int | str


class VerifierInfo(BaseModel):
    ok: Optional[bool] = None
    reason: Optional[str] = None
    revision_of: Optional[str] = None


class ProducerInfo(BaseModel):
    fit: Optional[bool] = None
    reason: Optional[str] = None
    score: Optional[float] = None


class RenderInfo(BaseModel):
    line: Optional[str] = None
    language: Optional[Literal["en", "ar"]] = None
    audio_url: Optional[str] = None
    duration_ms: Optional[int] = None


class Card(BaseModel):
    id: str
    agent: AgentName
    created_t: float
    text: str
    category: Literal["stat", "tactical", "background", "story"]
    player_ids: list[str] = Field(default_factory=list)
    team_id: Optional[TeamId] = None
    claims: list[Claim] = Field(default_factory=list)
    evidence_event_ids: list[int] = Field(default_factory=list)
    priority: int = 3
    time_sensitive: bool = True
    ttl_s: float = 30
    status: CardStatus = "proposed"
    verifier: VerifierInfo = Field(default_factory=VerifierInfo)
    producer: ProducerInfo = Field(default_factory=ProducerInfo)
    render: RenderInfo = Field(default_factory=RenderInfo)


class Directive(BaseModel):
    id: str
    type: Literal["focus_player", "more_topic", "less_topic", "avoid_topic", "mute_agent"]
    target: str
    expires_t: Optional[float] = None
    source: Literal["human", "auto"] = "human"
    text: str = ""


class InstanceSettings(BaseModel):
    id: str = "main"
    name: str = "EN Analyst"
    language: Literal["en", "ar"] = "en"
    audience: Literal["casual", "analyst"] = "analyst"
    perspective: Literal["neutral", "RED", "WHI"] = "neutral"
    energy: int = Field(3, ge=1, le=5)
    tone: Literal["neutral", "hype", "warm", "dry"] = "neutral"
    focus_player_id: Optional[str] = None
    ai_voice: bool = True
    muted_agents: list[AgentName] = Field(default_factory=list)
    directives: list[Directive] = Field(default_factory=list)


class InstancePatch(BaseModel):
    name: Optional[str] = None
    language: Optional[Literal["en", "ar"]] = None
    audience: Optional[Literal["casual", "analyst"]] = None
    perspective: Optional[Literal["neutral", "RED", "WHI"]] = None
    energy: Optional[int] = Field(None, ge=1, le=5)
    tone: Optional[Literal["neutral", "hype", "warm", "dry"]] = None
    focus_player_id: Optional[str] = None
    ai_voice: Optional[bool] = None


class ControlRequest(BaseModel):
    action: Literal["play", "pause", "speed", "seek"]
    value: Optional[float] = None


class DirectiveRequest(BaseModel):
    text: str


class MuteRequest(BaseModel):
    muted: bool


class SpeechMsg(BaseModel):
    type: Literal["speech"] = "speech"
    id: str
    kind: Literal["call", "card"]
    card_id: Optional[str] = None
    text: str
    subtitle_en: Optional[str] = None
    audio_url: Optional[str] = None
    play_at_t: float
    duration_ms: int
