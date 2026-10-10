// Answers repeat lookups without waiting for the USGS request gate.
const TTL_MS = 86_400_000;
const MAX_ENTRIES = 500;

export interface ElevationAnswer {
  status: 200 | 404;
  body: Record<string, unknown>;
}

const shared = globalThis as typeof globalThis & {
  vigilElevationCache?: Map<string, { at: number; answer: ElevationAnswer }>;
};
const cache = (shared.vigilElevationCache ??= new Map());

/** About 1 m of latitude; finer than EPQS resolution. */
export const elevationKey = (latitude: number, longitude: number) =>
  `${latitude.toFixed(5)},${longitude.toFixed(5)}`;

export function cachedElevation(key: string): ElevationAnswer | null {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.at > TTL_MS) {
    cache.delete(key);
    return null;
  }
  return entry.answer;
}

export function storeElevation(key: string, answer: ElevationAnswer) {
  cache.delete(key);
  cache.set(key, { at: Date.now(), answer });
  // Maps iterate in insertion order, so the first key is the oldest.
  if (cache.size > MAX_ENTRIES) cache.delete(cache.keys().next().value!);
}
