import { useEffect, useRef, useState } from "react";
import { ChevronDown, Moon, Pause, Play, Sun } from "lucide-react";
import Logo from "./Logo";
import { controlMatch } from "../api";
import { MOCK_MODE } from "../config";
import { useBoothStore } from "../store";
import { formatMatchClock } from "../utils/time";
import { useTheme } from "../utils/theme";

function probability(value: number | undefined) {
  const percent = (value ?? 0) * ((value ?? 0) <= 1 ? 100 : 1);
  return Math.round(percent);
}

export default function TopBar() {
  const clock = useBoothStore((state) => state.clock);
  const displayT = useBoothStore((state) => state.displayT);
  const events = useBoothStore((state) => state.events);
  const meta = useBoothStore((state) => state.meta);
  const stats = useBoothStore((state) => state.stats);
  const connection = useBoothStore((state) => state.connection);
  const costCapReached = useBoothStore((state) => state.costCapReached);
  const [jumpOpen, setJumpOpen] = useState(false);
  const [theme, toggleTheme] = useTheme();
  const jumpRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!jumpRef.current?.contains(event.target as Node)) setJumpOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const message = clock?.message;
  const red = meta?.teams.RED;
  const white = meta?.teams.WHI;
  const redControl = Math.round(stats?.control.RED ?? 50);
  const chaos = Math.round(stats?.chaos ?? 0);
  const chaosColor = chaos < 35 ? "#34d399" : chaos < 65 ? "#fbbf24" : "#fb4b5c";

  return (
    <header className="relative z-40 border-b border-white/[0.07] bg-[var(--sp-header)] shadow-[0_12px_36px_rgba(0,0,0,.25)]">
      <div className="flex h-[66px] items-center gap-5 px-4 2xl:px-6">
        <div className="flex w-[174px] shrink-0 items-center gap-3">
          <Logo size={36} />
          <div>
            <div className="text-[19px] font-black tracking-[0.22em] text-white">SPOTTER</div>
            <div className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">
              Live research booth
            </div>
          </div>
        </div>

        <div className="flex min-w-[265px] items-center gap-3 border-l border-white/[0.07] pl-5">
          <TeamScore name={red?.short_name ?? "REDMOOR"} color={red?.color_primary ?? "#d7263d"} />
          <div className="flex items-center gap-2 font-mono text-[25px] font-semibold tracking-tight text-white">
            <span>{message?.score[0] ?? 0}</span>
            <span className="text-sm font-normal text-slate-600">–</span>
            <span>{message?.score[1] ?? 0}</span>
          </div>
          <TeamScore name={white?.short_name ?? "WHITCLIFFE"} color={white?.color_primary ?? "#f2f2f2"} />
        </div>

        <div className="flex items-center gap-3 border-l border-white/[0.07] pl-5">
          <div className="min-w-[92px]">
            <div className="font-mono text-[25px] font-semibold leading-none tracking-[-0.05em] text-emerald-300 tabular-nums">
              {message ? formatMatchClock(displayT, message, events) : "--:--"}
            </div>
            <div className="mt-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
              {message?.period === 2 ? "2nd half" : "1st half"} · display
            </div>
          </div>
          <button
            className="icon-button h-9 w-9"
            title={message?.paused ? "Play" : "Pause"}
            aria-label={message?.paused ? "Play match" : "Pause match"}
            disabled={!message}
            onClick={() => void controlMatch({ action: message?.paused ? "play" : "pause" })}
          >
            {message?.paused ? <Play size={15} fill="currentColor" /> : <Pause size={15} fill="currentColor" />}
          </button>
          <div className="flex rounded-md border border-white/[0.08] bg-black/20 p-0.5">
            {[1, 2, 5].map((speed) => (
              <button
                key={speed}
                onClick={() => void controlMatch({ action: "speed", value: speed as 1 | 2 | 5 })}
                className={`h-7 min-w-8 rounded px-1.5 font-mono text-[13px] font-semibold transition ${
                  message?.speed === speed
                    ? "bg-white/[0.12] text-white shadow-sm"
                    : "text-slate-500 hover:text-slate-200"
                }`}
              >
                {speed}×
              </button>
            ))}
          </div>
          <div className="relative" ref={jumpRef}>
            <button
              className="flex h-9 items-center gap-2 rounded-md border border-white/[0.08] bg-white/[0.035] px-3 text-[13px] font-semibold text-slate-300 transition hover:bg-white/[0.08]"
              onClick={() => setJumpOpen((open) => !open)}
              aria-expanded={jumpOpen}
            >
              Jump <ChevronDown size={13} className={jumpOpen ? "rotate-180 transition" : "transition"} />
            </button>
            {jumpOpen && (
              <div className="absolute left-0 top-11 w-56 rounded-lg border border-white/10 bg-[var(--sp-panel-2)] p-1.5 shadow-2xl shadow-black/60">
                <div className="px-2.5 pb-1.5 pt-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
                  Key moment presets
                </div>
                <div className="grid grid-cols-4 gap-1">
                  {meta?.jump_presets.map((preset) => (
                    <button
                      key={preset.minute}
                      className="rounded-md px-2 py-2 font-mono text-xs text-slate-300 transition hover:bg-emerald-300/10 hover:text-emerald-300"
                      onClick={() => {
                        void controlMatch({ action: "seek", value: preset.minute });
                        setJumpOpen(false);
                      }}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          <span className={`h-1.5 w-1.5 rounded-full ${connection === "connected" ? "bg-emerald-400 shadow-[0_0_8px_#34d399]" : "bg-amber-400"}`} />
          <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">
            {MOCK_MODE ? "Mock feed" : connection}
          </span>
          <span className="rounded border border-white/[0.07] px-2 py-1 font-mono text-[11px] text-slate-600">
            −{message?.display_delay_s.toFixed(1) ?? "2.0"}s
          </span>
          <CostChip spent={message?.cost_usd} cap={message?.cost_cap_usd} />
          <button
            className="icon-button ml-1 h-9 w-9"
            title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            aria-label="Toggle light/dark theme"
            onClick={toggleTheme}
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>
      </div>

      <div className="flex h-[42px] items-center gap-6 border-t border-white/[0.05] px-4 2xl:px-6">
        <div className="flex min-w-[300px] flex-1 items-center gap-3">
          <span className="shrink-0 pr-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Control</span>
          <div className="flex h-[5px] min-w-24 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
            <div className="transition-[width] duration-500" style={{ width: `${redControl}%`, backgroundColor: red?.color_primary ?? "#d7263d" }} />
            <div className="transition-[width] duration-500" style={{ width: `${100 - redControl}%`, backgroundColor: white?.color_primary ?? "#f2f2f2" }} />
          </div>
          <span className="whitespace-nowrap font-mono text-[12px] text-slate-300">
            {red?.short_name ?? "Redmoor"} <strong className="font-semibold text-white">{redControl}%</strong>
          </span>
        </div>
        <div className="flex min-w-[240px] flex-1 items-center gap-3">
          <span className="shrink-0 pr-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Chaos</span>
          <div className="h-[5px] min-w-20 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-red-500 transition-[width] duration-500"
              style={{ width: `${chaos}%` }}
            />
          </div>
          <span className="w-6 font-mono text-[13px] font-semibold" style={{ color: chaosColor }}>{chaos}</span>
        </div>
        <div className="whitespace-nowrap font-mono text-[11px] uppercase tracking-[0.08em] text-slate-500">
          Win <span className="text-slate-300">R {probability(stats?.win_prob.RED)}</span>
          <span className="mx-1.5 text-slate-700">/</span>D {probability(stats?.win_prob.DRAW)}
          <span className="mx-1.5 text-slate-700">/</span>W {probability(stats?.win_prob.WHI)}
        </div>
        {costCapReached && (
          <div className="ml-auto rounded border border-red-400/40 bg-red-500/15 px-2.5 py-1 text-[11px] font-black uppercase tracking-[0.14em] text-red-300">
            Cost cap reached
          </div>
        )}
      </div>
    </header>
  );
}

function CostChip({ spent, cap }: { spent?: number; cap?: number }) {
  if (spent == null || !cap) return null;
  const share = spent / cap;
  const tone = share >= 0.8
    ? "border-red-400/40 bg-red-500/15 text-red-300"
    : share >= 0.5
      ? "border-amber-300/40 bg-amber-300/10 text-amber-300"
      : "border-white/[0.07] text-slate-400";
  return (
    <span className={`rounded border px-2 py-1 font-mono text-[11px] tabular-nums ${tone}`} title="Azure AI spend (models + voice) — hard cap">
      ${spent.toFixed(2)} / ${cap.toFixed(0)}
    </span>
  );
}

function TeamScore({ name, color }: { name: string; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2 w-2 shrink-0 rounded-full ring-2 ring-white/[0.12]" style={{ backgroundColor: color }} />
      <span className="text-[12px] font-bold tracking-[0.08em] text-slate-300">{name}</span>
    </div>
  );
}
