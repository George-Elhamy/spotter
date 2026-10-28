import { Volume2 } from "lucide-react";
import { useBoothStore } from "../store";

export default function SubtitleBar() {
  const speech = useBoothStore((state) => state.currentSpeech);
  const language = useBoothStore((state) => state.instance?.language ?? "en");
  const arabic = speech ? /[\u0600-\u06ff]/.test(speech.text) : false;
  void language;

  return (
    <section className="panel mt-2.5 min-h-[66px] shrink-0 px-4 py-2.5" aria-live="polite">
      <div className="flex h-full items-center gap-3">
        <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-md border ${speech ? "border-emerald-300/20 bg-emerald-300/[0.08] text-emerald-300" : "border-white/[0.06] bg-white/[0.025] text-slate-600"}`}>
          <Volume2 size={14} className={speech ? "subtitle-speaker" : ""} />
        </div>
        <div className="min-w-0 flex-1">
          {speech ? (
            <>
              <div dir={arabic ? "rtl" : "ltr"} className={`text-[15px] font-medium leading-snug text-slate-100 ${arabic ? "text-right" : ""}`}>
                <span className="mr-1.5 text-emerald-300">🔊</span>{speech.text}
              </div>
              {speech.subtitle_en && (
                <div dir="ltr" className="mt-1 text-[12px] leading-snug text-slate-500">{speech.subtitle_en}</div>
              )}
            </>
          ) : (
            <div>
              <div className="text-[13px] font-medium text-slate-500">Commentary channel ready</div>
              <div className="mt-1 text-[10px] uppercase tracking-[0.15em] text-slate-700">Synchronized to the broadcast delay</div>
            </div>
          )}
        </div>
        {speech && <span className="shrink-0 rounded border border-white/[0.06] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-slate-600">{speech.kind === "call" ? "Live call" : "Insight"}</span>}
      </div>
    </section>
  );
}
