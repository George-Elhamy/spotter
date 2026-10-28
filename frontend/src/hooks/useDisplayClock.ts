import { useEffect } from "react";
import { useBoothStore } from "../store";

export function useDisplayClock() {
  useEffect(() => {
    let frame = 0;
    const tick = (now: number) => {
      const { clock, setDisplayT } = useBoothStore.getState();
      if (clock) {
        const { message } = clock;
        const elapsed = message.paused ? 0 : ((now - clock.receivedAt) / 1000) * message.speed;
        setDisplayT(message.t + elapsed - message.display_delay_s);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);
}
