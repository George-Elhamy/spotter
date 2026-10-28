import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup } from "framer-motion";
import { Columns3 } from "lucide-react";
import { useBoothStore } from "../store";
import type { Card } from "../types/contract";
import CardItem from "./CardItem";

const proposedStatuses = new Set(["proposed", "verifying", "rejected", "revising"]);
const queueStatuses = new Set(["verified", "queued", "rendering", "ready", "airing"]);

export default function Board() {
  const cards = useBoothStore((state) => state.cards);
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const highlightTimer = useRef<number | null>(null);
  const allCards = useMemo(() => [...cards.values()], [cards]);

  const proposed = allCards
    .filter((card) => proposedStatuses.has(card.status))
    .sort((a, b) => b.created_t - a.created_t);
  const closed = allCards
    .filter((card) => card.status === "skipped" || card.status === "discarded")
    .sort((a, b) => b.created_t - a.created_t)
    .slice(0, 8);
  const queue = allCards
    .filter((card) => queueStatuses.has(card.status))
    .sort((a, b) => {
      if (a.status === "airing") return -1;
      if (b.status === "airing") return 1;
      return (b.producer.score ?? -Infinity) - (a.producer.score ?? -Infinity);
    });
  const aired = allCards
    .filter((card) => card.status === "aired")
    .sort((a, b) => b.created_t - a.created_t);
  const archive = allCards
    .filter((card) => card.status === "expired" || card.status === "removed")
    .sort((a, b) => b.created_t - a.created_t)
    .slice(0, 6);

  useEffect(() => () => {
    if (highlightTimer.current !== null) window.clearTimeout(highlightTimer.current);
  }, []);

  const showRevision = (id: string) => {
    setHighlighted(id);
    requestAnimationFrame(() => {
      document.querySelector(`[data-card-id="${CSS.escape(id)}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    if (highlightTimer.current !== null) window.clearTimeout(highlightTimer.current);
    highlightTimer.current = window.setTimeout(() => setHighlighted(null), 1800);
  };

  return (
    <section className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-white/[0.055] px-3">
        <Columns3 size={12} className="text-slate-500" />
        <h2 className="section-title">Booth board</h2>
        <span className="ml-auto font-mono text-[8px] uppercase tracking-wider text-slate-600">Verifier → producer → air</span>
      </div>
      <LayoutGroup>
        <div className="grid min-h-0 flex-1 grid-cols-3 divide-x divide-white/[0.055]">
          <BoardColumn title="Proposed" count={proposed.length + closed.length} accent="#94a3b8">
            <CardList cards={proposed} highlighted={highlighted} onRevision={showRevision} />
            {closed.length > 0 && (
              <div className="mt-2 shrink-0 border-t border-dashed border-white/[0.07] pt-2">
                <div className="mb-1.5 px-1 text-[7px] font-bold uppercase tracking-[0.14em] text-slate-700">Skipped / discarded</div>
                <CardList cards={closed} highlighted={highlighted} onRevision={showRevision} />
              </div>
            )}
          </BoardColumn>
          <BoardColumn title="Producer queue" count={queue.length} accent="#a78bfa">
            <CardList cards={queue} highlighted={highlighted} onRevision={showRevision} />
          </BoardColumn>
          <BoardColumn title="Aired" count={aired.length} accent="#34d399">
            <CardList cards={aired} highlighted={highlighted} onRevision={showRevision} />
            {archive.length > 0 && (
              <div className="mt-2 shrink-0 border-t border-dashed border-white/[0.07] pt-2">
                <div className="mb-1.5 px-1 text-[7px] font-bold uppercase tracking-[0.14em] text-slate-700">Expired / removed</div>
                <CardList cards={archive} highlighted={highlighted} onRevision={showRevision} compact />
              </div>
            )}
          </BoardColumn>
        </div>
      </LayoutGroup>
    </section>
  );
}

function BoardColumn({
  title,
  count,
  accent,
  children,
}: {
  title: string;
  count: number;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <div className="board-column flex min-h-0 flex-col">
      <div className="sticky top-0 z-10 flex h-8 shrink-0 items-center gap-1.5 border-b border-white/[0.045] bg-[#101518]/95 px-2.5 backdrop-blur">
        <span className="h-1 w-1 rounded-full" style={{ backgroundColor: accent }} />
        <h3 className="truncate text-[8px] font-bold uppercase tracking-[0.13em] text-slate-400">{title}</h3>
        <span className="ml-auto font-mono text-[8px] text-slate-600">{count}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-1.5">{children}</div>
    </div>
  );
}

function CardList({
  cards,
  highlighted,
  onRevision,
  compact = false,
}: {
  cards: Card[];
  highlighted: string | null;
  onRevision: (id: string) => void;
  compact?: boolean;
}) {
  if (!cards.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <AnimatePresence initial={false}>
        {cards.map((card) => (
          <CardItem
            key={card.id}
            card={card}
            highlighted={highlighted === card.id}
            compact={compact}
            onRevision={onRevision}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
