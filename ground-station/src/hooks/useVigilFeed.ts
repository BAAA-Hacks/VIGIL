import { deriveFeedStatus } from "../lib/feedStatus";
import { useEffect, useState } from "react";
import type {
  DemoScenario,
  DetectionResult,
  FeedMode,
  ThermalFrame,
} from "../types/vigil";
import { isThermalFrame, isDetectionResult } from "../lib/validation";
import { createDemoSample } from "../lib/demoFeed";
export function useVigilFeed() {
  const [mode, setMode] = useState<FeedMode>("demo");
  const [paused, setPaused] = useState(false);
  const [scenario, setScenario] = useState<DemoScenario>("human");
  const [frame, setFrame] = useState<ThermalFrame | null>(null);
  const [detection, setDetection] = useState<DetectionResult | null>(null);
  const [now, setNow] = useState(Date.now());
  const [received, setReceived] = useState(0);
  const [count, setCount] = useState(0);
  const demo = mode === "demo";
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!demo || paused || scenario === "disconnected") return;
    const tick = () => {
      const time = Date.now();
      const sample = createDemoSample(scenario, time);
      setFrame(sample.frame);
      setDetection(sample.detection);
      setReceived(time);
      setCount((c) => c + 1);
    };
    tick();
    const timer = setInterval(tick, 200);
    return () => clearInterval(timer);
  }, [demo, paused, scenario]);
  useEffect(() => {
    if (demo) return;
    const onFrame = (event: Event) => {
      if (!(event instanceof CustomEvent)) return;
      const value: unknown = event.detail;
      if (!isThermalFrame(value)) return;
      setFrame(value);
      setReceived(Date.now());
      setCount((count) => count + 1);
    };
    const onDetection = (event: Event) => {
      if (!(event instanceof CustomEvent)) return;
      const value: unknown = event.detail;
      if (isDetectionResult(value)) setDetection(value);
    };
    window.addEventListener("vigil:frame", onFrame);
    window.addEventListener("vigil:detection", onDetection);
    return () => {
      window.removeEventListener("vigil:frame", onFrame);
      window.removeEventListener("vigil:detection", onDetection);
    };
  }, [demo]);
  const { age, stale, disconnected, current, humans, status } =
    deriveFeedStatus({
      frame,
      detection,
      now,
      received,
      demo,
      paused,
      scenario,
    });
  function changeMode(value: FeedMode) {
    setMode(value);
    setFrame(null);
    setDetection(null);
    setReceived(0);
    setCount(0);
    setPaused(false);
  }

  return {
    mode,
    demo,
    paused,
    scenario,
    frame,
    current,
    humans,
    received,
    count,
    age,
    stale,
    disconnected,
    status,
    changeMode,
    setScenario,
    togglePause: () => setPaused((value) => !value),
    startDemo: () => {
      changeMode("demo");
      setScenario("human");
    },
  };
}
export type VigilFeed = ReturnType<typeof useVigilFeed>;
