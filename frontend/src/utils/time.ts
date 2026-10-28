import type { ClockMsg, MatchEvent } from "../types/contract";
import { latestDisplayedEvent } from "../store";

export function displayedMatchSeconds(
  displayT: number,
  clock: ClockMsg,
  events: MatchEvent[],
) {
  const latest = latestDisplayedEvent(events, displayT);
  if (latest) {
    return latest.minute * 60 + latest.second + Math.max(0, displayT - latest.t);
  }
  if (clock.period === 2) {
    const secondHalfStart = events.find((event) => event.period === 2);
    if (secondHalfStart) return 2700 + displayT - secondHalfStart.t;
    return Math.max(2700, displayT);
  }
  return displayT;
}

export function formatMatchClock(
  displayT: number,
  clock: ClockMsg,
  events: MatchEvent[],
) {
  const latest = latestDisplayedEvent(events, displayT);
  const period = latest?.period ?? clock.period;
  const seconds = Math.max(0, Math.floor(displayedMatchSeconds(displayT, clock, events)));
  const regularCap = period === 1 ? 2700 : 5400;
  const baseMinute = period === 1 ? 45 : 90;

  if (seconds > regularCap) {
    return `${baseMinute}+${Math.max(1, Math.ceil((seconds - regularCap) / 60))}`;
  }

  const bounded = period === 2 ? Math.max(2700, seconds) : seconds;
  const minutes = Math.floor(bounded / 60);
  const remainder = bounded % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function formatTimelineTime(t: number) {
  const seconds = Math.max(0, Math.floor(t));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
