import { create } from "zustand";
import type {
  AgentName,
  AgentStatus,
  Card,
  ClockMsg,
  Directive,
  InstanceSettings,
  MatchEvent,
  MatchMeta,
  SpeechMsg,
  StatsMsg,
  TraceMsg,
  WsMessage,
} from "./types/contract";

export interface ClockState {
  message: ClockMsg;
  receivedAt: number;
}

export interface AgentState {
  status: AgentStatus;
  last_ms: number | null;
}

export type ConnectionState = "connecting" | "connected" | "disconnected";

interface BoothState {
  clock: ClockState | null;
  displayT: number;
  meta: MatchMeta | null;
  instance: InstanceSettings | null;
  events: MatchEvent[];
  stats: StatsMsg | null;
  cards: Map<string, Card>;
  agentStatuses: Partial<Record<AgentName, AgentState>>;
  directives: Directive[];
  traces: TraceMsg[];
  speechQueue: SpeechMsg[];
  currentSpeech: SpeechMsg | null;
  costCapReached: boolean;
  connection: ConnectionState;
  resetVersion: number;
  setMeta: (meta: MatchMeta) => void;
  setInstance: (instance: InstanceSettings) => void;
  patchInstance: (patch: Partial<InstanceSettings>) => void;
  setConnection: (connection: ConnectionState) => void;
  setDisplayT: (displayT: number) => void;
  updateClock: (patch: Partial<Omit<ClockMsg, "type">>) => void;
  handleMessage: (message: WsMessage) => void;
  setCurrentSpeech: (speech: SpeechMsg | null) => void;
  removeSpeech: (id: string) => void;
}

export const useBoothStore = create<BoothState>((set) => ({
  clock: null,
  displayT: 0,
  meta: null,
  instance: null,
  events: [],
  stats: null,
  cards: new Map(),
  agentStatuses: {},
  directives: [],
  traces: [],
  speechQueue: [],
  currentSpeech: null,
  costCapReached: false,
  connection: "connecting",
  resetVersion: 0,

  setMeta: (meta) => set({ meta }),
  setInstance: (instance) => set({ instance, directives: instance.directives }),
  patchInstance: (patch) =>
    set((state) => ({
      instance: state.instance ? { ...state.instance, ...patch } : null,
      ...(patch.directives ? { directives: patch.directives } : {}),
    })),
  setConnection: (connection) => set({ connection }),
  setDisplayT: (displayT) =>
    set((state) => {
      const cutoff = displayT - 120;
      const shouldPrune = state.events.some((event) => event.t < cutoff);
      return {
        displayT,
        events: shouldPrune
          ? state.events.filter((event) => event.t >= cutoff)
          : state.events,
      };
    }),
  updateClock: (patch) =>
    set((state) => {
      if (!state.clock) return state;
      const previous = state.clock.message;
      const estimatedT = previous.paused
        ? previous.t
        : previous.t +
          ((performance.now() - state.clock.receivedAt) / 1000) * previous.speed;
      const message: ClockMsg = {
        ...previous,
        ...patch,
        t: patch.t ?? estimatedT,
        type: "clock",
      };
      return {
        clock: { message, receivedAt: performance.now() },
        costCapReached: message.cost_cap_reached,
      };
    }),

  handleMessage: (message) =>
    set((state) => {
      switch (message.type) {
        case "clock":
          return {
            clock: { message, receivedAt: performance.now() },
            costCapReached: message.cost_cap_reached,
          };
        case "event": {
          const events = state.events
            .filter((event) => event.id !== message.event.id)
            .concat(message.event)
            .sort((a, b) => a.t - b.t || a.id - b.id);
          return { events };
        }
        case "stats":
          return { stats: message };
        case "card": {
          const cards = new Map(state.cards);
          cards.set(message.card.id, message.card);
          return { cards };
        }
        case "agent_status":
          return {
            agentStatuses: {
              ...state.agentStatuses,
              [message.agent]: { status: message.status, last_ms: message.last_ms },
            },
          };
        case "speech": {
          if (state.speechQueue.some((speech) => speech.id === message.id)) {
            return state;
          }
          return {
            speechQueue: [...state.speechQueue, message].sort(
              (a, b) => a.play_at_t - b.play_at_t,
            ),
          };
        }
        case "directive":
          return {
            directives: message.directives,
            instance: state.instance
              ? { ...state.instance, directives: message.directives }
              : null,
          };
        case "trace":
          return { traces: [message, ...state.traces].slice(0, 50) };
        case "instance":
          return { instance: message.instance, directives: message.instance.directives };
        case "reset": {
          const delay = state.clock?.message.display_delay_s ?? 2;
          return {
            cards: new Map(),
            events: [],
            speechQueue: [],
            currentSpeech: null,
            traces: [],
            resetVersion: state.resetVersion + 1,
            displayT: message.t - delay,
            clock: state.clock
              ? {
                  message: { ...state.clock.message, t: message.t },
                  receivedAt: performance.now(),
                }
              : null,
          };
        }
      }
    }),

  setCurrentSpeech: (currentSpeech) => set({ currentSpeech }),
  removeSpeech: (id) =>
    set((state) => ({
      speechQueue: state.speechQueue.filter((speech) => speech.id !== id),
    })),
}));

export function latestDisplayedEvent(events: MatchEvent[], displayT: number) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].t <= displayT) return events[index];
  }
  return null;
}
