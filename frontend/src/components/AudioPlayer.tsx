import { useCallback, useEffect, useRef, useState } from "react";
import { Volume2 } from "lucide-react";
import { useBoothStore } from "../store";
import type { SpeechMsg } from "../types/contract";

export default function AudioPlayer() {
  const displayT = useBoothStore((state) => state.displayT);
  const queue = useBoothStore((state) => state.speechQueue);
  const aiVoice = useBoothStore((state) => state.instance?.ai_voice ?? false);
  const resetVersion = useBoothStore((state) => state.resetVersion);
  const setCurrentSpeech = useBoothStore((state) => state.setCurrentSpeech);
  const removeSpeech = useBoothStore((state) => state.removeSpeech);
  const [unlocked, setUnlocked] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const timerRef = useRef<number | null>(null);
  const currentRef = useRef<SpeechMsg | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const finish = useCallback(() => {
    clearTimer();
    const audio = audioRef.current;
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      audioRef.current = null;
    }
    currentRef.current = null;
    setCurrentSpeech(null);
  }, [clearTimer, setCurrentSpeech]);

  const start = useCallback((speech: SpeechMsg) => {
    if (currentRef.current) return;
    currentRef.current = speech;
    setCurrentSpeech(speech);
    removeSpeech(speech.id);

    const showForDuration = () => {
      if (currentRef.current?.id !== speech.id) return;
      clearTimer();
      timerRef.current = window.setTimeout(finish, Math.max(500, speech.duration_ms));
    };

    if (!aiVoice || !speech.audio_url || !unlocked) {
      showForDuration();
      return;
    }

    const audio = new Audio(speech.audio_url);
    audio.preload = "auto";
    audioRef.current = audio;
    let fellBack = false;
    const fallback = () => {
      if (fellBack || currentRef.current?.id !== speech.id) return;
      fellBack = true;
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      if (audioRef.current === audio) audioRef.current = null;
      showForDuration();
    };
    audio.onerror = fallback;
    audio.onended = finish;
    timerRef.current = window.setTimeout(finish, Math.max(1500, speech.duration_ms + 1500));
    void audio.play().catch(fallback);
  }, [aiVoice, clearTimer, finish, removeSpeech, setCurrentSpeech, unlocked]);

  useEffect(() => {
    if (currentRef.current) return;
    for (const speech of queue) {
      if (speech.kind === "call" && displayT - speech.play_at_t > 3) {
        removeSpeech(speech.id);
      }
    }
    const next = queue.find(
      (speech) => speech.play_at_t <= displayT + 0.06 &&
        !(speech.kind === "call" && displayT - speech.play_at_t > 3),
    );
    if (next) start(next);
  }, [displayT, queue, removeSpeech, start]);

  useEffect(() => {
    finish();
  }, [resetVersion, finish]);

  useEffect(() => () => {
    finish();
    void audioContextRef.current?.close();
  }, [finish]);

  const enableAudio = async () => {
    try {
      const context = audioContextRef.current ?? new AudioContext();
      audioContextRef.current = context;
      await context.resume();
      const source = context.createBufferSource();
      source.buffer = context.createBuffer(1, 1, context.sampleRate);
      source.connect(context.destination);
      source.start();
    } catch {
      // HTMLAudio can still be unlocked by this user gesture on some browsers.
    } finally {
      setUnlocked(true);
    }
  };

  if (unlocked || !aiVoice) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-50 flex justify-center">
      <button
        onClick={() => void enableAudio()}
        className="pointer-events-auto flex items-center gap-2.5 rounded-full border border-emerald-300/30 bg-[#10251d]/95 px-5 py-3 text-[11px] font-semibold text-emerald-100 shadow-2xl shadow-black/60 backdrop-blur-xl transition hover:scale-[1.02] hover:bg-[#163328]"
      >
        <Volume2 size={15} className="text-emerald-300" />
        Click to enable audio
        <span className="rounded-full bg-emerald-300/10 px-2 py-0.5 text-[8px] uppercase tracking-wider text-emerald-300">One time</span>
      </button>
    </div>
  );
}
