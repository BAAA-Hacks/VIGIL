import type {
  DetectionResult,
  DemoScenario,
  ThermalFrame,
} from "../types/vigil";
const STALE_AFTER_MS = 2_000;
const DISCONNECTED_AFTER_MS = 5_000;
interface FeedSnapshot {
  frame: ThermalFrame | null;
  detection: DetectionResult | null;
  now: number;
  received: number;
  demo: boolean;
  paused: boolean;
  scenario: DemoScenario;
}
export function deriveFeedStatus({
  frame,
  detection,
  now,
  received,
  demo,
  paused,
  scenario,
}: FeedSnapshot) {
  const age = received ? Math.max(0, now - received) : Infinity;
  const stale = age > STALE_AFTER_MS;
  const disconnected =
    (demo && scenario === "disconnected") || age > DISCONNECTED_AFTER_MS;
  const matched = frame !== null && detection?.frame_id === frame.frame_id;
  const current = matched && !stale ? detection : null;
  const humans =
    current?.detections.filter(
      (item) => item.class.toLowerCase() === "human",
    ) ?? [];
  const status = disconnected
    ? "Disconnected"
    : stale
      ? "Feed stale"
      : paused
        ? "Paused"
        : demo
          ? "Demo feed"
          : "Live feed";
  return { age, stale, disconnected, current, humans, status };
}
