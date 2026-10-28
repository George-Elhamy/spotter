import { useState } from "react";
import { ChevronDown, ExternalLink, TerminalSquare } from "lucide-react";
import { useBoothStore } from "../store";
import { formatTimelineTime } from "../utils/time";

export default function TracePanel() {
  const traces = useBoothStore((state) => state.traces);
  const [expanded, setExpanded] = useState(true);

  return (
    <section className="panel shrink-0 overflow-hidden">
      <div className="flex h-8 items-center gap-2 px-3">
        <TerminalSquare size={11} className="text-slate-600" />
        <button className="flex items-center gap-2" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
          <span className="section-title">System trace</span>
          <span className="font-mono text-[8px] text-slate-700">{traces.length}</span>
          <ChevronDown size={11} className={`text-slate-600 transition ${expanded ? "" : "-rotate-90"}`} />
        </button>
        <a href="/api/audit" target="_blank" rel="noreferrer" className="ml-auto flex items-center gap-1 text-[8px] text-slate-600 transition hover:text-emerald-300">
          Audit log <ExternalLink size={9} />
        </a>
      </div>
      {expanded && (
        <div className="h-[92px] overflow-y-auto border-t border-white/[0.05] bg-black/15 px-3 py-1.5 font-mono text-[8px] leading-relaxed">
          {traces.length ? traces.map((trace, index) => (
            <div key={`${trace.t}-${trace.agent}-${index}`} className="flex gap-2 border-b border-white/[0.035] py-1 last:border-0">
              <span className="shrink-0 text-slate-700">{formatTimelineTime(trace.t)}</span>
              <span className={`shrink-0 ${trace.action.includes("reject") || trace.action.includes("error") ? "text-red-400" : "text-emerald-300/70"}`}>{trace.agent}.{trace.action}</span>
              <span className="min-w-0 truncate text-slate-600" title={trace.detail}>{trace.detail}</span>
            </div>
          )) : (
            <div className="grid h-full place-items-center text-slate-700">Agent and recovery events will appear here</div>
          )}
        </div>
      )}
    </section>
  );
}
