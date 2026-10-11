import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { detectPocketPort } from "../src/lib/pocketPort.ts";

test("finds the Pocket among serial devices and ignores the flight controller", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "by-id-"));
  writeFileSync(path.join(dir, "usb-INAV_REDSTART_0x8000000-if00"), "");
  assert.equal(detectPocketPort(dir), undefined);
  const pocket = "usb-EdgeTX_Radiomaster_Pocket_Serial_Port_00000000001B-if00";
  writeFileSync(path.join(dir, pocket), "");
  assert.equal(detectPocketPort(dir), path.join(dir, pocket));
  assert.equal(detectPocketPort(path.join(dir, "missing")), undefined);
});
