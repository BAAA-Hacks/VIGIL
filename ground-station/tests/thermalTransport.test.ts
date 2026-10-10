import test from "node:test";
import assert from "node:assert/strict";
import {
  thermalFrame,
  thermalDetections,
  ThermalPairs,
} from "../src/lib/thermalTransport.ts";
import { createThermalRelay } from "../scripts/thermal-relay.ts";
import { io } from "socket.io-client";
import { once } from "node:events";

const frame = (id = "frame-1", timestamp = 1000) => ({
  frame_id: id,
  capture_timestamp_ms: timestamp,
  camera_timestamp_ms: 123,
  width: 160,
  height: 120,
  image_data_url: "data:image/png;base64,aGVsbG8=",
});
const person = {
  class: "person",
  bbox: [0.1, 0.2, 0.3, 0.8],
  bottom_center: [0.2, 0.8],
  confidence: 0.91,
  tracking_id: 1,
  feet_visible: true,
  center_temperature_c: 29.4,
};
const detection = (
  id = "frame-1",
  timestamp = 1000,
  persons: unknown[] = [person],
) => ({
  frame_id: id,
  capture_timestamp_ms: timestamp,
  processing_ms: 7.25,
  persons,
});

test("maps the real producer schema and omits nullable fields", () => {
  assert.equal(thermalFrame(frame())?.timestamp_ms, 1000);
  assert.equal(thermalFrame(frame())?.payload, frame().image_data_url);
  const result = thermalDetections(detection())!;
  assert.equal(result.detections[0].track_id, "1");
  assert.equal(result.detections[0].temperature_c, 29.4);
  const nullable = thermalDetections(
    detection("frame-1", 1000, [
      { ...person, tracking_id: null, center_temperature_c: null },
    ]),
  )!;
  assert.equal("track_id" in nullable.detections[0], false);
  assert.equal("temperature_c" in nullable.detections[0], false);
});

test("drops individual invalid people, accepts empty detections and rejects unsafe envelopes", () => {
  const raw = detection("frame-1", 1000, [
    person,
    { ...person, bbox: [0.1, 0.2, 0.1, 0.8] },
    { ...person, bottom_center: [0.8, 0.8] },
    { ...person, confidence: NaN },
  ]);
  assert.equal(thermalDetections(raw)?.detections.length, 1);
  assert.deepEqual(
    thermalDetections(detection("frame-1", 1000, []))?.detections,
    [],
  );
  assert.equal(thermalFrame({ ...frame(), width: 320 }), null);
  assert.equal(
    thermalFrame({ ...frame(), image_data_url: "javascript:alert(1)" }),
    null,
  );
  assert.equal(thermalDetections({ ...detection(), persons: null }), null);
  const clipped = {
    ...person,
    bbox: [0.1, 0.2, 0.3, 1],
    bottom_center: [0.2, 1],
  };
  assert.equal(
    thermalDetections(detection("frame-1", 1000, [clipped]))?.detections[0]
      .feet_visible,
    false,
  );
});

test("pairs either order and rejects mismatches, duplicates, old frames and unbounded pending data", () => {
  const pairs = new ThermalPairs();
  assert.equal(pairs.push("detection", detection()), null);
  assert.equal(pairs.push("frame", frame())?.detection.frame_id, "frame-1");
  pairs.push("frame", frame());
  assert.equal(pairs.push("detection", detection()), null);
  pairs.push("frame", frame("mismatch", 2000));
  assert.equal(pairs.push("detection", detection("mismatch", 2001)), null);
  pairs.push("frame", frame("old", 999));
  assert.equal(pairs.push("detection", detection("old", 999)), null);
  for (let n = 0; n < 40; n++)
    pairs.push("frame", frame(`pending-${n}`, 3000 + n));
  assert.equal(pairs.push("detection", detection("pending-0", 3000)), null);
  assert.ok(pairs.push("detection", detection("pending-39", 3039)));
  pairs.reset();
  pairs.push("frame", frame());
  assert.ok(pairs.push("detection", detection()));
});

test("real Socket.IO relay broadcasts producer events and releases publisher on reconnect", async (t) => {
  const relay = createThermalRelay();
  relay.http.listen(0, "127.0.0.1");
  await once(relay.http, "listening");
  const address = relay.http.address();
  assert.ok(address && typeof address !== "string");
  const url = `http://127.0.0.1:${address.port}`;
  const consumer = io(url, { autoConnect: false, reconnection: false });
  const publisher = io(url, { autoConnect: false, reconnection: false });
  t.after(async () => {
    consumer.close();
    publisher.close();
    await new Promise<void>((resolve) => relay.io.close(() => resolve()));
  });
  const connect = (socket: typeof consumer) =>
    new Promise<void>((resolve, reject) => {
      socket.once("connect", resolve);
      socket.once("connect_error", reject);
      socket.connect();
    });
  await Promise.all([connect(consumer), connect(publisher)]);
  const pairs = new ThermalPairs();
  const received = new Promise<void>((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error("Thermal pair not received")),
      3000,
    );
    consumer.on("vigil:frame", (raw) => pairs.push("frame", raw));
    consumer.on("vigil:detection", (raw) => {
      const pair = pairs.push("detection", raw);
      if (pair) {
        clearTimeout(timer);
        assert.equal(pair.frame.frame_id, "frame-1");
        resolve();
      }
    });
  });
  publisher.emit("vigil:frame", frame());
  publisher.emit("vigil:detection", detection());
  await received;
  const serverDisconnect = once(
    relay.io.of("/").sockets.get(publisher.id!)!,
    "disconnect",
  );
  publisher.disconnect();
  await serverDisconnect;
  await connect(publisher);
  const empty = new Promise<void>((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error("Reconnect did not resume detections")),
      3000,
    );
    consumer.once("vigil:detection", (raw) => {
      clearTimeout(timer);
      assert.deepEqual(raw.persons, []);
      resolve();
    });
  });
  publisher.emit("vigil:detection", detection("frame-2", 2000, []));
  await empty;
});
