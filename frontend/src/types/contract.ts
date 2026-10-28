// Shared API contract — mirrors SPOTTER_SPEC.md §5.6, §7.1, §9, §10 exactly.
// Backend mirror: backend/app/models.py. Change both together.

export type TeamId = "RED" | "WHI";
export type PlayerId = string; // e.g. "RED-7", "WHI-10"

export interface XY {
  x: number; // 0..105 (metres)
  y: number; // 0..68
}

export interface FramePlayer {
  id: PlayerId;
  x: number;
  y: number;
}

export interface Frame {
  ball: XY;
  players: FramePlayer[]; // all players on pitch (22, or 21 after the red card)
}

export type EventType =
  | "kickoff" | "pass" | "carry" | "dribble" | "shot" | "save" | "goal" | "tackle"
  | "interception" | "clearance" | "block" | "duel" | "foul" | "card" | "free_kick"
  | "corner" | "throw_in" | "goal_kick" | "offside" | "var_check" | "var_decision"
  | "penalty_awarded" | "penalty_taken" | "injury" | "stoppage" | "substitution"
  | "added_time" | "half_time" | "full_time";

export type Restart = "throw_in" | "goal_kick" | "free_kick" | "corner" | "kickoff" | "penalty";
export type CardColor = "yellow" | "second_yellow" | "red";

export interface MatchEvent {
  id: number;
  t: number; // match seconds since kickoff (continuous; stoppage included)
  period: 1 | 2;
  minute: number;
  second: number;
  added: number;
  type: EventType;
  subtype?: string | null; // cross, header, long_ball, cutback, penalty, through_ball ...
  team_id: TeamId | null;
  player_id: PlayerId | null;
  related_player_id?: PlayerId | null;
  start?: XY | null;
  end?: XY | null;
  outcome?: string | null; // complete | incomplete | saved | goal | off_target | blocked | won | lost ...
  under_pressure?: boolean;
  body_part?: string | null;
  xg?: number | null;
  ball_speed_kmh?: number | null;
  flight_s?: number | null;
  restart?: Restart | null;
  card?: CardColor | null;
  var?: { check: string; decision: string } | null;
  frame: Frame;
}

// ---- Cards (§7.1) ----
export type AgentName = "stats_scout" | "tactical" | "dossier" | "storyline";
export type CardCategory = "stat" | "tactical" | "background" | "story";
export type CardStatus =
  | "proposed" | "verifying" | "rejected" | "revising" | "verified" | "skipped" | "queued"
  | "rendering" | "ready" | "airing" | "aired" | "expired" | "removed" | "discarded";

export interface Claim {
  kind: "stat" | string;
  entity: string;
  metric: string;
  against?: string | null;
  window?: string | null;
  value: number | string;
}

export interface Card {
  id: string;
  agent: AgentName;
  created_t: number;
  text: string;
  category: CardCategory;
  player_ids: PlayerId[];
  team_id: TeamId | null;
  claims: Claim[];
  evidence_event_ids: number[];
  priority: number; // 1-5
  time_sensitive: boolean;
  ttl_s: number;
  status: CardStatus;
  verifier: { ok: boolean | null; reason: string | null; revision_of: string | null };
  producer: { fit: boolean | null; reason: string | null; score: number | null };
  render: { line: string | null; language: Language | null; audio_url: string | null; duration_ms: number | null };
}

// ---- Instance settings (§9) ----
export type Language = "en" | "es" | "fr" | "de";
export type Audience = "casual" | "analyst";
export type Perspective = "neutral" | TeamId;
export type Tone = "neutral" | "hype" | "warm" | "dry";

export type DirectiveType = "focus_player" | "more_topic" | "less_topic" | "avoid_topic" | "mute_agent";
export interface Directive {
  id: string;
  type: DirectiveType;
  target: string;
  expires_t: number | null;
  source: "human" | "auto"; // auto = adaptation from removals (§7.5)
  text: string; // original chat text or auto reason, shown on chip
}

export interface InstanceSettings {
  id: string;
  name: string;
  language: Language;
  audience: Audience;
  perspective: Perspective;
  energy: 1 | 2 | 3 | 4 | 5;
  tone: Tone;
  focus_player_id: PlayerId | null;
  ai_voice: boolean;
  muted_agents: AgentName[];
  directives: Directive[];
}

// ---- REST: GET /api/match/meta ----
export interface Player {
  id: PlayerId;
  team_id: TeamId;
  number: number;
  name: string;
  short_name: string; // surname, used on name tags
  position: string;
  nationality: string;
  starter: boolean;
}

export interface Team {
  id: TeamId;
  name: string;
  short_name: string;
  color_primary: string; // hex
  color_secondary: string; // hex (number text)
  formation: string;
  manager: string;
  stadium: string;
}

export interface JumpPreset {
  minute: number;
  label: string;
}

export interface MatchMeta {
  teams: Record<TeamId, Team>;
  players: Player[];
  jump_presets: JumpPreset[]; // §11: 0,8,17,26,37,51,60,66,80,87,90
  key_moments: { t: number; minute: number; label: string }[];
  duration_t: number; // final event t
}

// POST /api/match/control
export type ControlAction =
  | { action: "play"; value?: null }
  | { action: "pause"; value?: null }
  | { action: "speed"; value: 1 | 2 | 5 }
  | { action: "seek"; value: number }; // minute

export interface AuditEntry {
  t: number;
  kind: "call" | "card";
  card_id: string | null;
  agent: AgentName | "caller";
  text: string;
  language: Language;
}

// ---- WebSocket /ws (server → client) ----
export interface ClockMsg {
  type: "clock";
  t: number;
  display_delay_s: number;
  speed: number;
  period: 1 | 2;
  score: [number, number]; // [RED, WHI]
  paused: boolean;
  cost_cap_reached: boolean; // §0.1 cost guard badge
  cost_usd: number; // running total from backend/app/data/cost_ledger.json
  cost_cap_usd: number; // COST_CAP_USD
}
export interface EventMsg { type: "event"; event: MatchEvent }
export interface StatsMsg {
  type: "stats";
  control: Record<TeamId, number>; // sums to 100
  chaos: number; // 0-100
  possession: { match: Record<TeamId, number>; rolling: Record<TeamId, number> };
  win_prob: { RED: number; DRAW: number; WHI: number };
}
export interface CardMsg { type: "card"; card: Card }
export type AgentStatus = "idle" | "thinking" | "muted" | "error";
export interface AgentStatusMsg { type: "agent_status"; agent: AgentName; status: AgentStatus; last_ms: number | null }
export interface SpeechMsg {
  type: "speech";
  id: string;
  kind: "call" | "card";
  card_id: string | null;
  text: string;
  subtitle_en: string | null;
  audio_url: string | null; // null = subtitle only
  play_at_t: number; // display-time (match seconds)
  duration_ms: number;
}
export interface DirectiveMsg { type: "directive"; directives: Directive[] }
export interface TraceMsg { type: "trace"; t: number; agent: string; action: string; detail: string }
export interface ResetMsg { type: "reset"; t: number } // sent on seek: client clears board/audio/event buffer
export interface InstanceMsg { type: "instance"; instance: InstanceSettings }

export type WsMessage =
  | ClockMsg | EventMsg | StatsMsg | CardMsg | AgentStatusMsg | SpeechMsg
  | DirectiveMsg | TraceMsg | ResetMsg | InstanceMsg;
