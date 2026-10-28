import { Volume2, VolumeX } from "lucide-react";
import { muteAgent } from "../api";
import { useBoothStore } from "../store";
import type { AgentName } from "../types/contract";

export const AGENTS: { id: AgentName; label: string; color: string }[] = [
  { id: "stats_scout", label: "Stats", color: "#60a5fa" },
  { id: "tactical", label: "Tactics", color: "#c084fc" },
  { id: "dossier", label: "Dossier", color: "#2dd4bf" },
  { id: "storyline", label: "Story", color: "#fb923c" },
];

export default function AgentStrip() {
  const statuses = useBoothStore((state) => state.agentStatuses);
  const mutedAgents = useBoothStore((state) => state.instance?.muted_agents ?? []);

  return (
    <section className="panel shrink-0 p-2">
      <div className="grid grid-cols-4 gap-1.5">
        {AGENTS.map((agent) => {
          const state = statuses[agent.id];
          const muted = mutedAgents.includes(agent.id) || state?.status === "muted";
          const status = muted ? "muted" : state?.status ?? "idle";
          return (
            <div key={agent.id} className="flex min-w-0 items-center gap-2 rounded-md border border-white/[0.055] bg-black/15 px-2.5 py-2">
              <span className={`status-dot status-${status}`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className={`truncate text-[10px] font-semibold ${muted ? "text-slate-600" : "text-slate-200"}`}>{agent.label}</span>
                  {muted && <span className="text-[9px]">🔇</span>}
                </div>
                <div className="mt-0.5 font-mono text-[8px] uppercase tracking-wide text-slate-600">
                  {status === "thinking" ? "thinking" : state?.last_ms != null ? formatMs(state.last_ms) : status}
                </div>
              </div>
              <button
                className={`shrink-0 rounded p-1 transition ${muted ? "text-slate-600 hover:text-slate-300" : "text-slate-500 hover:bg-white/[0.06] hover:text-white"}`}
                title={muted ? `Unmute ${agent.label}` : `Mute ${agent.label}`}
                aria-label={muted ? `Unmute ${agent.label}` : `Mute ${agent.label}`}
                onClick={() => void muteAgent(agent.id, !muted)}
              >
                {muted ? <VolumeX size={12} /> : <Volume2 size={12} />}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function formatMs(ms: number) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}
