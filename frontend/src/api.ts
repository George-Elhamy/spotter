import mockInstance from "../mock/instance.json";
import mockMeta from "../mock/meta.json";
import { MOCK_MODE } from "./config";
import { useBoothStore } from "./store";
import type {
  AgentName,
  AuditEntry,
  ControlAction,
  Directive,
  DirectiveType,
  InstanceSettings,
  MatchMeta,
  SpeechMsg,
} from "./types/contract";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed (${response.status})`);
  }
  return (await response.json()) as T;
}

function jsonRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export async function getMatchMeta(): Promise<MatchMeta> {
  if (MOCK_MODE) return structuredClone(mockMeta) as MatchMeta;
  return request<MatchMeta>("/api/match/meta");
}

export async function getInstance(): Promise<InstanceSettings> {
  if (MOCK_MODE) return structuredClone(mockInstance) as InstanceSettings;
  return request<InstanceSettings>("/api/instance");
}

export async function patchInstance(
  patch: Partial<InstanceSettings>,
): Promise<InstanceSettings> {
  if (MOCK_MODE) {
    const store = useBoothStore.getState();
    store.patchInstance(patch);
    return useBoothStore.getState().instance!;
  }
  return jsonRequest<InstanceSettings>("/api/instance", "PATCH", patch);
}

export async function controlMatch(action: ControlAction): Promise<void> {
  if (!MOCK_MODE) {
    await jsonRequest<unknown>("/api/match/control", "POST", action);
    return;
  }

  const store = useBoothStore.getState();
  if (action.action === "seek") {
    const t = action.value * 60;
    store.handleMessage({ type: "reset", t });
    store.updateClock({ t, period: action.value >= 45 ? 2 : 1 });
    return;
  }
  if (action.action === "play") store.updateClock({ paused: false });
  if (action.action === "pause") store.updateClock({ paused: true });
  if (action.action === "speed") store.updateClock({ speed: action.value });
}

function parseDirective(text: string): DirectiveType {
  const value = text.toLowerCase();
  if (value.startsWith("focus")) return "focus_player";
  if (value.startsWith("less")) return "less_topic";
  if (value.startsWith("avoid")) return "avoid_topic";
  if (value.startsWith("mute")) return "mute_agent";
  return "more_topic";
}

function directiveTarget(text: string, type: DirectiveType): string {
  if (type === "focus_player") {
    const query = text.replace(/^focus(?:\s+on)?\s*/i, "").trim().toLowerCase();
    const players = useBoothStore.getState().meta?.players ?? [];
    const player = players.find((candidate) => {
      const name = candidate.name.toLowerCase();
      const shortName = candidate.short_name.toLowerCase();
      return query === shortName || query === name || name.includes(query) || shortName.includes(query);
    });
    return player?.id ?? query;
  }
  if (type === "mute_agent") {
    const value = text.toLowerCase();
    if (value.includes("stat")) return "stats_scout";
    if (value.includes("tactic")) return "tactical";
    if (value.includes("dossier")) return "dossier";
    if (value.includes("story")) return "storyline";
  }
  return text.replace(/^(more|less|avoid|mute)\s*/i, "").trim() || text;
}

export async function postDirective(text: string): Promise<Directive> {
  if (!MOCK_MODE) return jsonRequest<Directive>("/api/directive", "POST", { text });

  const store = useBoothStore.getState();
  const type = parseDirective(text);
  const directive: Directive = {
    id: `d_local_${Date.now()}`,
    type,
    target: directiveTarget(text, type),
    expires_t: null,
    source: "human",
    text,
  };
  const directives = [...store.directives, directive];
  store.handleMessage({ type: "directive", directives });
  return directive;
}

export async function deleteDirective(id: string): Promise<void> {
  if (!MOCK_MODE) {
    await request<unknown>(`/api/directive/${encodeURIComponent(id)}`, { method: "DELETE" });
    return;
  }
  const store = useBoothStore.getState();
  store.handleMessage({
    type: "directive",
    directives: store.directives.filter((directive) => directive.id !== id),
  });
}

export async function muteAgent(name: AgentName, muted: boolean): Promise<void> {
  if (!MOCK_MODE) {
    await jsonRequest<unknown>(`/api/agents/${name}/mute`, "POST", { muted });
    return;
  }
  const store = useBoothStore.getState();
  if (store.instance) {
    const mutedAgents = new Set(store.instance.muted_agents);
    if (muted) mutedAgents.add(name);
    else mutedAgents.delete(name);
    store.patchInstance({ muted_agents: [...mutedAgents] });
  }
  store.handleMessage({
    type: "agent_status",
    agent: name,
    status: muted ? "muted" : "idle",
    last_ms: store.agentStatuses[name]?.last_ms ?? null,
  });
}

export async function removeCard(id: string): Promise<void> {
  if (!MOCK_MODE) {
    await jsonRequest<unknown>(`/api/cards/${encodeURIComponent(id)}/remove`, "POST");
    return;
  }
  const store = useBoothStore.getState();
  const card = store.cards.get(id);
  if (card) store.handleMessage({ type: "card", card: { ...card, status: "removed" } });
}

export async function sayCardNow(id: string): Promise<void> {
  if (!MOCK_MODE) {
    await jsonRequest<unknown>(`/api/cards/${encodeURIComponent(id)}/say-now`, "POST");
    return;
  }
  const store = useBoothStore.getState();
  const card = store.cards.get(id);
  if (!card) return;
  store.handleMessage({ type: "card", card: { ...card, status: "airing" } });
  if (card.render.line) {
    const speech: SpeechMsg = {
      type: "speech",
      id: `s_local_${card.id}`,
      kind: "card",
      card_id: card.id,
      text: card.render.line,
      subtitle_en: card.render.language && card.render.language !== "en" ? card.text : null,
      audio_url: card.render.audio_url,
      play_at_t: store.displayT,
      duration_ms: card.render.duration_ms ?? 3000,
    };
    store.handleMessage(speech);
  }
}

export function getAudioUrl(id: string) {
  return `/api/audio/${encodeURIComponent(id)}.mp3`;
}

export async function getAudio(id: string): Promise<Blob> {
  if (MOCK_MODE) return new Blob();
  const response = await fetch(getAudioUrl(id));
  if (!response.ok) throw new Error(`Audio request failed (${response.status})`);
  return response.blob();
}

export async function getAudit(): Promise<AuditEntry[]> {
  if (MOCK_MODE) return [];
  return request<AuditEntry[]>("/api/audit");
}

export async function getHealth(): Promise<Record<string, unknown>> {
  if (MOCK_MODE) return { status: "ok", mode: "mock" };
  return request<Record<string, unknown>>("/api/health");
}
