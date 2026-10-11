"use client";
import { useEffect, useState } from "react";

const POLL_MS = 2000;

/** Pause/resume for ./replay.sh. `available` is false unless a replay is running. */
export function useReplayControl() {
  const [available, setAvailable] = useState(false);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const state = await (await fetch("/api/replay")).json();
        if (cancelled) return;
        setAvailable(state.available === true);
        setPaused(state.paused === true);
      } catch {
        if (!cancelled) setAvailable(false);
      }
    };
    void poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);
  async function toggle() {
    const next = !paused;
    setPaused(next);
    try {
      const state = await (
        await fetch("/api/replay", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paused: next }),
        })
      ).json();
      setAvailable(state.available === true);
      setPaused(state.paused === true);
    } catch {
      setPaused(!next);
    }
  }
  return { available, paused, toggle };
}
