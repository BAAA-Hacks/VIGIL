import type { PinData } from "../types/mission.ts";

/**
 * Every tracked person found this session. A person in view shows their latest pin (position
 * and capture); one who leaves the view keeps their last pin, marked `inView: false`.
 * People are numbered 1, 2, 3 in the order they were first found, and keep that number.
 * Detections without a track ID are only shown while in view: their IDs change every frame.
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
      this.people.set(pin.id, {
        ...pin,
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
