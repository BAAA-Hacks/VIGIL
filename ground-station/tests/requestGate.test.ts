import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequestGate } from "../src/lib/requestGate.ts";
test("request starts are at least five seconds apart, including after failure", async () => {
  let time = 0;
  const starts: number[] = [];
  const gate = createRequestGate(
    5100,
    () => time,
    async (milliseconds) => {
      time += milliseconds;
    },
  );
  const first = gate(async () => {
    starts.push(time);
    throw new Error("Service failure");
  });
  const second = gate(async () => {
    starts.push(time);
    return 1;
  });
  const third = gate(async () => {
    starts.push(time);
    return 2;
  });
  await Promise.allSettled([first, second, third]);
  assert.deepEqual(starts, [0, 5100, 10200]);
});
