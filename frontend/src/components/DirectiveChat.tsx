import { useState } from "react";
import { ArrowUp, MessageSquareText, X } from "lucide-react";
import { deleteDirective, postDirective } from "../api";
import { useBoothStore } from "../store";

const suggestions = ["focus on Novak", "more tactics", "less stats"];

export default function DirectiveChat() {
  const directives = useBoothStore((state) => state.directives);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  const submit = async () => {
    const value = text.trim();
    if (!value || sending) return;
    setSending(true);
    try {
      await postDirective(value);
      setText("");
    } catch (error) {
      console.error("Could not add directive", error);
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="panel flex min-h-0 flex-1 flex-col p-3.5">
      <div className="flex items-center gap-2">
        <MessageSquareText size={13} className="text-emerald-300" />
        <h2 className="section-title">Showrunner directives</h2>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">Steer the producer without leaving the booth.</p>

      <form
        className="mt-3 flex items-center gap-1.5 rounded-md border border-white/[0.09] bg-black/25 p-1.5 focus-within:border-emerald-300/30"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Tell the booth…"
          className="min-w-0 flex-1 bg-transparent px-1 text-[13px] text-slate-200 outline-none placeholder:text-slate-600"
        />
        <button
          type="submit"
          disabled={!text.trim() || sending}
          aria-label="Send directive"
          className="grid h-6 w-6 shrink-0 place-items-center rounded bg-emerald-300 text-[#0a1511] transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-25"
        >
          <ArrowUp size={13} strokeWidth={2.5} />
        </button>
      </form>

      <div className="mt-2 flex flex-wrap gap-1">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            onClick={() => setText(suggestion)}
            className="rounded-full border border-white/[0.07] px-2 py-1 text-[10px] text-slate-500 transition hover:border-white/15 hover:text-slate-300"
          >
            {suggestion}
          </button>
        ))}
      </div>

      <div className="mt-3 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-0.5">
        {directives.length === 0 ? (
          <div className="rounded-md border border-dashed border-white/[0.06] px-3 py-3 text-center text-[11px] text-slate-600">
            No active directives
          </div>
        ) : (
          directives.map((directive) => (
            <div
              key={directive.id}
              className={`group flex items-center gap-2 rounded-md border px-2.5 py-2 text-[12px] ${
                directive.source === "auto"
                  ? "border-amber-300/15 bg-amber-300/[0.055] text-amber-100/75"
                  : "border-emerald-300/15 bg-emerald-300/[0.055] text-emerald-100/85"
              }`}
            >
              <span className="min-w-0 flex-1 truncate" title={directive.text}>{directive.text}</span>
              {directive.source === "auto" && (
                <span className="rounded bg-amber-300/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-300/70">auto</span>
              )}
              <button
                aria-label={`Remove directive ${directive.text}`}
                onClick={() => void deleteDirective(directive.id)}
                className="text-slate-600 transition hover:text-white"
              >
                <X size={12} />
              </button>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
