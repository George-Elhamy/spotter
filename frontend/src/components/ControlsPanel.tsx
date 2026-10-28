import { patchInstance } from "../api";
import { useBoothStore } from "../store";
import type { InstanceSettings, Language } from "../types/contract";

export default function ControlsPanel() {
  const instance = useBoothStore((state) => state.instance);
  const meta = useBoothStore((state) => state.meta);
  const updateLocal = useBoothStore((state) => state.patchInstance);
  const setInstance = useBoothStore((state) => state.setInstance);

  if (!instance) return null;

  const update = async (patch: Partial<InstanceSettings>) => {
    const previous = instance;
    updateLocal(patch);
    try {
      setInstance(await patchInstance(patch));
    } catch (error) {
      console.error("Could not update instance settings", error);
      setInstance(previous);
    }
  };

  return (
    <section className="panel shrink-0 p-3.5">
      <PanelHeading title="Broadcast controls" detail="Personalize the feed" />
      <div className="mt-3.5 space-y-3.5">
        <div>
          <FieldLabel>Language</FieldLabel>
          <Segmented
            value={instance.language}
            options={[["en", "EN"], ["es", "ES"], ["fr", "FR"], ["de", "DE"]]}
            onChange={(language) => void update({ language: language as Language })}
          />
        </div>
        <div>
          <FieldLabel>Audience</FieldLabel>
          <Segmented
            value={instance.audience}
            options={[["casual", "Casual"], ["analyst", "Analyst"]]}
            onChange={(audience) => void update({ audience: audience as "casual" | "analyst" })}
          />
        </div>
        <div>
          <FieldLabel>Fans of</FieldLabel>
          <div className="grid grid-cols-3 rounded-md border border-white/[0.07] bg-black/20 p-0.5">
            {([["neutral", "Neutral"], ["RED", "Redmoor"], ["WHI", "Whitcliffe"]] as const).map(([value, label]) => (
              <button
                key={value}
                onClick={() => void update({ perspective: value })}
                className={`rounded px-1 py-1.5 text-[11px] font-semibold transition ${
                  instance.perspective === value ? "bg-white/[0.11] text-white" : "text-slate-500 hover:text-slate-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="flex items-baseline justify-between">
            <FieldLabel>Energy</FieldLabel>
            <span className="font-mono text-[11px] text-emerald-300">{instance.energy}/5</span>
          </div>
          <div className="flex items-end gap-1.5" role="radiogroup" aria-label="Commentary energy">
            {([1, 2, 3, 4, 5] as const).map((energy) => {
              const active = energy <= instance.energy;
              return (
                <button
                  key={energy}
                  role="radio"
                  aria-checked={energy === instance.energy}
                  aria-label={`Energy ${energy}`}
                  title={`Energy ${energy}`}
                  onClick={() => void update({ energy })}
                  style={{ height: `${18 + energy * 4}px` }}
                  className={`flex flex-1 items-end justify-center rounded-md border pb-1 font-mono text-[11px] font-semibold transition hover:-translate-y-0.5 ${
                    active
                      ? "border-emerald-300/40 bg-emerald-300/[0.18] text-emerald-200"
                      : "border-white/[0.08] bg-white/[0.03] text-slate-500 hover:border-emerald-300/30 hover:text-slate-200"
                  }`}
                >
                  {energy}
                </button>
              );
            })}
          </div>
          <div className="mt-1 flex justify-between text-[10px] uppercase tracking-[0.14em] text-slate-600">
            <span>Calm</span>
            <span>Hype</span>
          </div>
        </div>
        <label className="block">
          <FieldLabel>Tone</FieldLabel>
          <select
            className="field-select"
            value={instance.tone}
            onChange={(event) => void update({ tone: event.target.value as InstanceSettings["tone"] })}
          >
            <option value="neutral">Neutral</option>
            <option value="hype">Hype</option>
            <option value="warm">Warm</option>
            <option value="dry">Dry</option>
          </select>
        </label>
        <label className="block">
          <FieldLabel>Focus player</FieldLabel>
          <select
            className="field-select"
            value={instance.focus_player_id ?? ""}
            onChange={(event) => void update({ focus_player_id: event.target.value || null })}
          >
            <option value="">No player focus</option>
            {(["RED", "WHI"] as const).map((teamId) => (
              <optgroup key={teamId} label={meta?.teams[teamId].name ?? teamId}>
                {meta?.players.filter((player) => player.team_id === teamId).map((player) => (
                  <option key={player.id} value={player.id}>
                    #{player.number} {player.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="flex cursor-pointer items-center justify-between border-t border-white/[0.06] pt-3">
          <span>
            <span className="block text-[13px] font-medium text-slate-200">AI voice</span>
            <span className="mt-0.5 block text-[11px] text-slate-500">Speak rendered commentary</span>
          </span>
          <input
            type="checkbox"
            className="peer sr-only"
            checked={instance.ai_voice}
            onChange={(event) => void update({ ai_voice: event.target.checked })}
          />
          <span className="relative h-5 w-9 rounded-full bg-white/10 transition peer-checked:bg-emerald-400/80 after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-slate-300 after:transition after:content-[''] peer-checked:after:translate-x-4 peer-checked:after:bg-white" />
        </label>
      </div>
    </section>
  );
}

function PanelHeading({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <h2 className="section-title">{title}</h2>
      <span className="text-[10px] uppercase tracking-wider text-slate-600">{detail}</span>
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.13em] text-slate-500">{children}</span>;
}

function Segmented({
  value,
  options,
  onChange,
}: {
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <div
      className="grid rounded-md border border-white/[0.07] bg-black/20 p-0.5"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {options.map(([option, label]) => (
        <button
          key={option}
          onClick={() => onChange(option)}
          className={`rounded px-2 py-1.5 text-[12px] font-semibold transition ${
            value === option ? "bg-white/[0.11] text-white shadow-sm" : "text-slate-500 hover:text-slate-300"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
