import { readdirSync } from "node:fs";
import path from "node:path";

/** Serial device of a RadioMaster Pocket (EdgeTX) plugged in over USB, if there is one (Linux). */
export function detectPocketPort(
  dir = "/dev/serial/by-id",
): string | undefined {
  try {
    const name = readdirSync(dir).find((entry) =>
      /edgetx|radiomaster/i.test(entry),
    );
    return name ? path.join(dir, name) : undefined;
  } catch {
    return undefined; // no serial devices, or not Linux
  }
}
