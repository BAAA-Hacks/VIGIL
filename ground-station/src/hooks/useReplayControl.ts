"use client";
import { useEffect, useRef, useState } from "react";

const POLL_MS = 2000;

/** Pause/resume for ./replay.sh (button or Space). `available` is false unless a replay is running. */
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
  const toggleRef = useRef<() => void>(() => {});
  useEffect(() => {
    if (!available) return;
    const onKey = (event: KeyboardEvent) => {
      if (
        event.code !== "Space" ||
        event.repeat ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey
      )
        return;
      const target = event.target as HTMLElement | null;
      // Leave Space alone where it types or activates something.
      if (target?.closest("input, textarea, select, button, [contenteditable]"))
        return;
      event.preventDefault();
      toggleRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [available]);
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
  toggleRef.current = toggle;
  return { available, paused, toggle };
}
