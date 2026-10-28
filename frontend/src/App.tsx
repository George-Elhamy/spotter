import { useEffect, useState } from "react";
import { Radio } from "lucide-react";
import { getInstance, getMatchMeta } from "./api";
import AgentStrip from "./components/AgentStrip";
import AudioPlayer from "./components/AudioPlayer";
import Board from "./components/Board";
import ControlsPanel from "./components/ControlsPanel";
import DirectiveChat from "./components/DirectiveChat";
import Pitch from "./components/Pitch";
import SubtitleBar from "./components/SubtitleBar";
import TopBar from "./components/TopBar";
import TracePanel from "./components/TracePanel";
import { useDisplayClock } from "./hooks/useDisplayClock";
import { connectSpotter } from "./socket";
import { useBoothStore } from "./store";

export default function App() {
  const meta = useBoothStore((state) => state.meta);
  const instance = useBoothStore((state) => state.instance);
  const [bootError, setBootError] = useState<string | null>(null);
  useDisplayClock();

  useEffect(() => {
    let active = true;
    const connection = connectSpotter(
      (message) => useBoothStore.getState().handleMessage(message),
      (state) => useBoothStore.getState().setConnection(state),
    );

    void Promise.all([getMatchMeta(), getInstance()])
      .then(([matchMeta, settings]) => {
        if (!active) return;
        useBoothStore.getState().setMeta(matchMeta);
        useBoothStore.getState().setInstance(settings);
      })
      .catch((error: unknown) => {
        if (active) {
          console.error("Could not initialize Spotter", error);
          setBootError(error instanceof Error ? error.message : "Could not initialize Spotter");
        }
      });

    return () => {
      active = false;
      connection.close();
    };
  }, []);

  if (!meta || !instance) {
    return (
      <div className="grid h-dvh place-items-center bg-[var(--sp-bg)] text-white">
        <div className="text-center">
          <div className="mx-auto grid h-11 w-11 place-items-center rounded-xl border border-emerald-300/20 bg-emerald-300/[0.07]">
            <Radio size={21} className="animate-pulse text-emerald-300" />
          </div>
          <div className="mt-4 text-lg font-black tracking-[0.25em]">SPOTTER</div>
          <div className="mt-2 text-[9px] uppercase tracking-[0.2em] text-slate-600">
            {bootError ?? "Connecting to the research booth"}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell flex h-dvh flex-col overflow-hidden text-slate-200">
      <TopBar />
      <main className="grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)_minmax(560px,40%)] gap-2.5 p-2.5">
        <aside className="flex min-h-0 flex-col gap-2.5">
          <ControlsPanel />
          <DirectiveChat />
        </aside>
        <section className="flex min-h-0 min-w-0 flex-col">
          <Pitch />
          <SubtitleBar />
        </section>
        <aside className="flex min-h-0 min-w-0 flex-col gap-2.5">
          <AgentStrip />
          <Board />
          <TracePanel />
        </aside>
      </main>
      <AudioPlayer />
      {bootError && <div className="fixed bottom-3 left-3 z-50 rounded bg-red-500/15 px-3 py-2 text-xs text-red-200">{bootError}</div>}
    </div>
  );
}
