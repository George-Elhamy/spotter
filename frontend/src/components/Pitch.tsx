import { useMemo } from "react";
import { Radio } from "lucide-react";
import { latestDisplayedEvent, useBoothStore } from "../store";
import type { FramePlayer, MatchEvent, Player, XY } from "../types/contract";

function interpolate(a: XY, b: XY, amount: number): XY {
  return { x: a.x + (b.x - a.x) * amount, y: a.y + (b.y - a.y) * amount };
}

function eventLabel(event: MatchEvent | null) {
  if (!event) return "Waiting for the next phase of play";
  const type = event.subtype ? `${event.type} · ${event.subtype}` : event.type;
  return type.replaceAll("_", " ");
}

export default function Pitch() {
  const events = useBoothStore((state) => state.events);
  const displayT = useBoothStore((state) => state.displayT);
  const meta = useBoothStore((state) => state.meta);
  const focusPlayerId = useBoothStore((state) => state.instance?.focus_player_id ?? null);
  const playerById = useMemo(
    () => new Map<string, Player>(meta?.players.map((player) => [player.id, player]) ?? []),
    [meta],
  );

  let previous: MatchEvent | null = null;
  let next: MatchEvent | null = null;
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].t <= displayT) {
      previous = events[index];
      next = events[index + 1] ?? null;
      break;
    }
  }
  if (!previous && events.length) next = events[0];

  const fromFrame = previous?.frame ?? next?.frame;
  const toFrame = next?.frame ?? previous?.frame;
  const amount = previous && next && next.t > previous.t
    ? Math.min(1, Math.max(0, (displayT - previous.t) / (next.t - previous.t)))
    : 0;

  const nextPlayers = new Map(toFrame?.players.map((player) => [player.id, player]) ?? []);
  const previousPlayers = new Map(fromFrame?.players.map((player) => [player.id, player]) ?? []);
  const playerIds = new Set([...previousPlayers.keys(), ...nextPlayers.keys()]);
  const players: FramePlayer[] = [...playerIds].flatMap((id) => {
    const from = previousPlayers.get(id);
    const to = nextPlayers.get(id);
    if (!from && !to) return [];
    const position = from && to ? interpolate(from, to, amount) : from ?? to!;
    return [{ id, ...position }];
  });
  const ball = fromFrame && toFrame ? interpolate(fromFrame.ball, toFrame.ball, amount) : { x: 52.5, y: 34 };
  const displayedEvent = latestDisplayedEvent(events, displayT);
  const carrier = displayedEvent?.player_id ? playerById.get(displayedEvent.player_id) : null;
  const carrierPosition = players.find((player) => player.id === carrier?.id);
  const goal = [...events].reverse().find(
    (event) => event.type === "goal" && event.t <= displayT && displayT - event.t <= 3,
  );
  const goalScorer = goal?.player_id ? playerById.get(goal.player_id) : null;
  const shots = events.filter(
    (event) => event.type === "shot" && event.t <= displayT && displayT - event.t <= 0.85,
  );

  return (
    <section className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-white/[0.055] px-3.5">
        <div className="flex items-center gap-2">
          <Radio size={12} className="text-emerald-300" />
          <h2 className="section-title">Match ingestion</h2>
          <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-[7px] font-black uppercase tracking-[0.16em] text-red-400">Live</span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[8px] uppercase tracking-[0.12em] text-slate-600">
          <span>105 × 68 m</span><span className="text-slate-800">/</span><span>2D tracking</span>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-[#09110e] p-2">
        <svg
          viewBox="-3 -3 111 74"
          className="h-auto max-h-full w-full"
          role="img"
          aria-label="Live two-dimensional football pitch"
        >
          <defs>
            <linearGradient id="pitchBase" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#15392b" />
              <stop offset="1" stopColor="#0d2b21" />
            </linearGradient>
            <filter id="playerShadow" x="-100%" y="-100%" width="300%" height="300%">
              <feDropShadow dx="0" dy="0.45" stdDeviation="0.45" floodColor="#000" floodOpacity="0.65" />
            </filter>
            <filter id="ballShadow" x="-200%" y="-200%" width="500%" height="500%">
              <feDropShadow dx="0" dy="0.25" stdDeviation="0.3" floodColor="#000" floodOpacity="0.8" />
            </filter>
          </defs>

          <rect x="-3" y="-3" width="111" height="74" rx="1" fill="#09150f" />
          <rect width="105" height="68" fill="url(#pitchBase)" />
          {Array.from({ length: 10 }, (_, index) => (
            <rect
              key={index}
              x={index * 10.5}
              width="10.5"
              height="68"
              fill={index % 2 ? "#ffffff" : "#000000"}
              opacity={index % 2 ? 0.017 : 0.035}
            />
          ))}
          <line x1="0" y1="34" x2="105" y2="34" stroke="#b9d8c8" strokeOpacity="0.07" strokeWidth="0.12" />
          <line x1="52.5" y1="0" x2="52.5" y2="68" stroke="#b9d8c8" strokeOpacity="0.07" strokeWidth="0.12" />

          <g fill="none" stroke="#d7e9de" strokeOpacity="0.58" strokeWidth="0.18">
            <rect x="0.1" y="0.1" width="104.8" height="67.8" />
            <line x1="52.5" y1="0" x2="52.5" y2="68" />
            <circle cx="52.5" cy="34" r="9.15" />
            <rect x="0" y="13.84" width="16.5" height="40.32" />
            <rect x="88.5" y="13.84" width="16.5" height="40.32" />
            <rect x="0" y="24.84" width="5.5" height="18.32" />
            <rect x="99.5" y="24.84" width="5.5" height="18.32" />
            <path d="M 16.5 26.68 A 9.15 9.15 0 0 1 16.5 41.32" />
            <path d="M 88.5 26.68 A 9.15 9.15 0 0 0 88.5 41.32" />
            <path d="M 0 1 A 1 1 0 0 0 1 0 M 104 0 A 1 1 0 0 0 105 1 M 0 67 A 1 1 0 0 1 1 68 M 104 68 A 1 1 0 0 1 105 67" />
            <rect x="-2" y="30.34" width="2" height="7.32" strokeOpacity="0.35" />
            <rect x="105" y="30.34" width="2" height="7.32" strokeOpacity="0.35" />
          </g>
          <g fill="#d7e9de" fillOpacity="0.65">
            <circle cx="52.5" cy="34" r="0.28" />
            <circle cx="11" cy="34" r="0.28" />
            <circle cx="94" cy="34" r="0.28" />
          </g>

          {shots.map((shot) => {
            const location = shot.start ?? shot.frame.ball;
            return (
              <g key={shot.id} transform={`translate(${location.x} ${location.y})`}>
                <circle className="shot-ring" r="1.5" fill="none" stroke="#fde68a" strokeWidth="0.42" />
                <circle className="shot-ring shot-ring-delay" r="1" fill="none" stroke="#fff7ed" strokeWidth="0.22" />
              </g>
            );
          })}

          <g filter="url(#playerShadow)">
            {players.map((player) => {
              const details = playerById.get(player.id);
              const team = details ? meta?.teams[details.team_id] : null;
              const focused = player.id === focusPlayerId;
              return (
                <g key={player.id} data-player-id={player.id} transform={`translate(${player.x} ${player.y})`}>
                  {focused && <circle className="focus-ring" r="2.15" fill="none" stroke="#fde047" strokeWidth="0.38" />}
                  <circle r="1.43" fill={team?.color_primary ?? "#94a3b8"} stroke={focused ? "#fde047" : "#07110d"} strokeWidth={focused ? 0.28 : 0.18} />
                  <text
                    textAnchor="middle"
                    dominantBaseline="central"
                    y="0.08"
                    fill={team?.color_secondary ?? "#111111"}
                    fontSize="1.55"
                    fontWeight="800"
                    fontFamily="ui-monospace, monospace"
                  >
                    {details?.number ?? "?"}
                  </text>
                </g>
              );
            })}
          </g>

          <g transform={`translate(${ball.x} ${ball.y})`} filter="url(#ballShadow)">
            <circle r="0.73" fill="#f8fafc" stroke="#152019" strokeWidth="0.2" />
            <circle r="0.19" fill="#26352d" />
          </g>

          {carrier && carrierPosition && (
            <g transform={`translate(${carrierPosition.x} ${carrierPosition.y - 3.25})`} pointerEvents="none">
              <rect x={-(carrier.short_name.length * 0.43 + 1.15)} y="-1.3" width={carrier.short_name.length * 0.86 + 2.3} height="2.35" rx="0.65" fill="#07100d" fillOpacity="0.9" stroke="#d1fae5" strokeOpacity="0.18" strokeWidth="0.1" />
              <text textAnchor="middle" y="0.37" fill="#f0fdf4" fontSize="1.35" fontWeight="650" fontFamily="system-ui, sans-serif">
                {carrier.short_name}
              </text>
            </g>
          )}
        </svg>

        {goal && (
          <div className="goal-overlay pointer-events-none absolute inset-0 grid place-items-center overflow-hidden">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(5,15,11,.15),rgba(5,12,9,.78))]" />
            <div className="relative text-center">
              <div className="goal-word text-[clamp(56px,8vw,118px)] font-black italic leading-none tracking-[-0.07em] text-white drop-shadow-[0_8px_35px_rgba(0,0,0,.6)]">
                GOAL
              </div>
              <div className="mx-auto mt-2 w-fit rounded-full border border-white/20 bg-black/45 px-5 py-1.5 text-[12px] font-bold uppercase tracking-[0.22em] text-emerald-200 backdrop-blur-md">
                {goalScorer?.short_name ?? "Redmoor"} · {goal?.team_id ? meta?.teams[goal.team_id]?.short_name : ""}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex h-8 shrink-0 items-center gap-2.5 border-t border-white/[0.055] px-3.5 text-[9px]">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${displayedEvent ? "bg-emerald-300" : "bg-slate-600"}`} />
        <span className="shrink-0 font-mono text-slate-500">
          {displayedEvent ? `${String(displayedEvent.minute).padStart(2, "0")}:${String(displayedEvent.second).padStart(2, "0")}` : "--:--"}
        </span>
        <span className="truncate capitalize text-slate-300">{eventLabel(displayedEvent)}</span>
        {displayedEvent?.player_id && <span className="ml-auto shrink-0 font-medium text-slate-500">{playerById.get(displayedEvent.player_id)?.short_name}</span>}
      </div>
    </section>
  );
}
