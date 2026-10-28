import { motion } from "framer-motion";
import { Check, LoaderCircle, X, Zap } from "lucide-react";
import { removeCard, sayCardNow } from "../api";
import { useBoothStore } from "../store";
import type { Card } from "../types/contract";
import { AGENTS } from "./AgentStrip";

const TERMINAL = new Set(["aired", "expired", "removed", "discarded", "skipped"]);
const RING_LENGTH = 2 * Math.PI * 10;

export default function CardItem({
  card,
  highlighted,
  compact = false,
  onRevision,
}: {
  card: Card;
  highlighted: boolean;
  compact?: boolean;
  onRevision: (id: string) => void;
}) {
  const displayT = useBoothStore((state) => state.displayT);
  const agent = AGENTS.find((candidate) => candidate.id === card.agent);
  const terminal = TERMINAL.has(card.status);
  const greyed = ["skipped", "discarded", "expired", "removed"].includes(card.status);
  const remaining = Math.max(0, card.created_t + card.ttl_s - displayT);
  const ttlRatio = Math.min(1, Math.max(0, remaining / card.ttl_s));
  const urgent = remaining < 10 && !terminal;

  return (
    <motion.article
      layout="position"
      layoutId={card.id}
      data-card-id={card.id}
      data-status={card.status}
      initial={{ opacity: 0, y: 8, scale: 0.985 }}
      animate={{ opacity: greyed ? 0.5 : 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 420, damping: 34, mass: 0.75 }}
      className={`card-item relative shrink-0 overflow-hidden rounded-md border bg-[var(--sp-panel-2)] ${card.status === "rejected" ? "card-rejected border-red-400/35" : "border-white/[0.075]"} ${highlighted ? "card-highlighted" : ""} ${compact ? "px-2.5 py-2" : "px-3 py-2.5"}`}
      style={{ borderLeft: `2px solid ${agent?.color ?? "#94a3b8"}` }}
    >
      <div className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: agent?.color }} />
        <span className="text-[8px] font-bold uppercase tracking-[0.14em]" style={{ color: agent?.color }}>{agent?.label}</span>
        <span className="font-mono text-[7px] uppercase tracking-wider text-slate-600">{card.status.replace("_", " ")}</span>
        {card.status === "verifying" && <LoaderCircle size={9} className="animate-spin text-slate-500" />}
        {card.status === "airing" && <span className="on-air-badge ml-auto">On air</span>}
        {card.verifier.ok === true && card.status !== "airing" && (
          <span className="ml-auto flex items-center gap-0.5 rounded-sm border border-emerald-300/20 bg-emerald-300/[0.06] px-1 py-0.5 text-[7px] font-bold uppercase tracking-wider text-emerald-300">
            <Check size={8} strokeWidth={3} /> Verified
          </span>
        )}
        {card.producer.score != null && card.status !== "airing" && (
          <span className={`${card.verifier.ok ? "" : "ml-auto"} rounded bg-white/[0.045] px-1.5 py-0.5 font-mono text-[8px] text-slate-400`} title="Producer score">
            {Math.round(card.producer.score)}
          </span>
        )}
      </div>

      <p className={`mt-2 leading-[1.45] text-slate-300 ${compact ? "line-clamp-2 text-[9px]" : "text-[10px]"}`}>
        {card.text}
      </p>
      {["ready", "airing", "aired"].includes(card.status) && card.render.line && (
        <p className="mt-1.5 border-l border-white/10 pl-2 text-[9px] italic leading-relaxed text-slate-500">“{card.render.line}”</p>
      )}

      {(card.status === "rejected" || card.status === "discarded") && card.verifier.reason && (
        <div className="mt-2 rounded border border-red-400/15 bg-red-400/[0.055] px-2 py-1.5 text-[8px] leading-relaxed text-red-300/85">
          {card.verifier.reason}
        </div>
      )}
      {card.status === "skipped" && card.producer.reason && (
        <div className="mt-1.5 text-[8px] italic leading-relaxed text-slate-500">Skipped · {card.producer.reason}</div>
      )}
      {card.verifier.revision_of && (
        <button
          onClick={() => onRevision(card.verifier.revision_of!)}
          className="mt-1.5 block font-mono text-[8px] text-purple-300/75 underline decoration-purple-300/20 underline-offset-2 transition hover:text-purple-200"
        >
          ↳ revised from {card.verifier.revision_of}
        </button>
      )}

      <div className="mt-2 flex min-h-[20px] items-center gap-2">
        {!terminal ? (
          <>
            <div className="flex items-center gap-1.5" title={`${Math.ceil(remaining)} seconds until expiry`}>
              <svg viewBox="0 0 26 26" className="h-[22px] w-[22px] -rotate-90">
                <circle cx="13" cy="13" r="10" fill="none" stroke="rgba(255,255,255,.07)" strokeWidth="2" />
                <circle
                  cx="13" cy="13" r="10" fill="none"
                  stroke={urgent ? "#fb7185" : "#64748b"}
                  strokeWidth="2" strokeLinecap="round"
                  strokeDasharray={RING_LENGTH}
                  strokeDashoffset={RING_LENGTH * (1 - ttlRatio)}
                />
              </svg>
              <span className={`font-mono text-[8px] ${urgent ? "text-red-300" : "text-slate-600"}`}>
                {formatRemaining(remaining)}
              </span>
            </div>
            <div className="ml-auto flex items-center gap-1">
              <button className="card-action hover:text-red-300" title="Remove card" aria-label={`Remove ${card.id}`} onClick={() => void removeCard(card.id)}>
                <X size={11} />
              </button>
              <button className="card-action hover:text-amber-300" title="Say now" aria-label={`Say ${card.id} now`} onClick={() => void sayCardNow(card.id)}>
                <Zap size={11} />
              </button>
            </div>
          </>
        ) : (
          <span className="font-mono text-[7px] uppercase tracking-wider text-slate-700">
            {card.status === "aired" ? "Delivered to broadcast" : card.status}
          </span>
        )}
      </div>
    </motion.article>
  );
}

function formatRemaining(seconds: number) {
  const rounded = Math.max(0, Math.ceil(seconds));
  return `${String(Math.floor(rounded / 60)).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
}
