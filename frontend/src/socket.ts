import mockStream from "../mock/ws_stream.json";
import { MOCK_MODE } from "./config";
import type { ClockMsg, WsMessage } from "./types/contract";

interface StreamEntry {
  at_ms: number;
  msg: WsMessage;
}

export interface SpotterConnection {
  close: () => void;
}

type MessageHandler = (message: WsMessage) => void;
type ConnectionHandler = (state: "connecting" | "connected" | "disconnected") => void;

function connectMock(onMessage: MessageHandler, onConnection: ConnectionHandler): SpotterConnection {
  const stream = mockStream as unknown as StreamEntry[];
  const timers = new Set<number>();
  let closed = false;

  const later = (callback: () => void, delay: number) => {
    const timer = window.setTimeout(() => {
      timers.delete(timer);
      if (!closed) callback();
    }, delay);
    timers.add(timer);
  };

  const replay = (looping: boolean) => {
    if (closed) return;
    if (looping) {
      const firstClock = stream.find((entry) => entry.msg.type === "clock")?.msg as
        | ClockMsg
        | undefined;
      onMessage({ type: "reset", t: firstClock?.t ?? 0 });
    }
    for (const entry of stream) {
      later(() => onMessage(entry.msg), entry.at_ms);
    }
    const end = stream.at(-1)?.at_ms ?? 0;
    later(() => replay(true), end + 750);
  };

  onConnection("connected");
  replay(false);

  return {
    close: () => {
      closed = true;
      timers.forEach((timer) => window.clearTimeout(timer));
      timers.clear();
    },
  };
}

function connectLive(onMessage: MessageHandler, onConnection: ConnectionHandler): SpotterConnection {
  let socket: WebSocket | null = null;
  let reconnectTimer: number | null = null;
  let attempt = 0;
  let closed = false;

  const connect = () => {
    if (closed) return;
    onConnection("connecting");
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${window.location.host}/ws`);

    socket.onopen = () => {
      attempt = 0;
      onConnection("connected");
    };
    socket.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data) as WsMessage);
      } catch (error) {
        console.warn("Spotter ignored an invalid WebSocket message", error);
      }
    };
    socket.onerror = () => socket?.close();
    socket.onclose = () => {
      if (closed) return;
      onConnection("disconnected");
      const delay = Math.min(10_000, 500 * 2 ** attempt) + Math.random() * 250;
      attempt += 1;
      reconnectTimer = window.setTimeout(connect, delay);
    };
  };

  connect();

  return {
    close: () => {
      closed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    },
  };
}

export function connectSpotter(
  onMessage: MessageHandler,
  onConnection: ConnectionHandler,
): SpotterConnection {
  return MOCK_MODE
    ? connectMock(onMessage, onConnection)
    : connectLive(onMessage, onConnection);
}
