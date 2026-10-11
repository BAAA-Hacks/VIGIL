import type { PinData } from "../types/mission.ts";

/** Photos at or above this detection confidence are clear enough to replace the shown one. */
export const PHOTO_MIN_CONFIDENCE = 0.7;
const confidence = (pin?: PinData) => pin?.review?.detection.confidence ?? -1;

/**
 * Every tracked person found this session. A person in view shows their latest pin (position
 * and capture); one who leaves the view keeps their last pin, marked `inView: false`.
 * People are numbered 1, 2, 3 in the order they were first found, and keep that number.
 * Detections without a track ID are only shown while in view: their IDs change every frame.
 *
 * The position always follows the latest detection, but the photo is the latest one at or
 * above PHOTO_MIN_CONFIDENCE (a clearer, fuller view of the person and surroundings); until a
 * person has one, it is their most confident photo so far.
 */
export class PersonMemory {
  private readonly numbers = new Map<string, number>();
  private readonly people = new Map<string, PinData>();

  /** The person's number, assigned on first request so slots never collide. */
  numberFor(id: string): number {
    let number = this.numbers.get(id);
    if (number === undefined) {
      number = this.numbers.size + 1;
      this.numbers.set(id, number);
    }
    return number;
  }

  update(livePins: PinData[], now: number): PinData[] {
    const inView = new Set<string>();
    const untracked: PinData[] = [];
    for (const pin of livePins) {
      if (pin.id.includes(":")) {
        untracked.push({ ...pin, inView: true });
        continue;
      }
      const number = this.numberFor(pin.id);
      const previous = this.people.get(pin.id);
      const keepPhoto =
        previous?.review !== undefined &&
        confidence(pin) < PHOTO_MIN_CONFIDENCE &&
        confidence(previous) >= confidence(pin);
      this.people.set(pin.id, {
        ...pin,
        ...(keepPhoto ? { review: previous!.review } : {}),
        displayLabel: String(number),
        name: `Person ${number}`,
        lastSeenAt: pin.capturedAt ?? now,
      });
      inView.add(pin.id);
    }
    const remembered = [...this.people.entries()]
      .sort((a, b) => this.numberFor(a[0]) - this.numberFor(b[0]))
      .map(([id, pin]) => ({ ...pin, inView: inView.has(id) }));
    return [...remembered, ...untracked];
  }

  clear() {
    this.numbers.clear();
    this.people.clear();
  }
}
