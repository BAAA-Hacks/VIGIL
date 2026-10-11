# Ground telemetry bridge

```
drone (INAV, CRSF telemetry) → RP1 → ELRS → Pocket (EdgeTX) → USB serial → telemetry_bridge.py → VehicleTelemetry JSON → UI
```

Downlink only for now. Nothing on the drone depends on this link: unplugging the Pocket's USB or killing the script changes nothing in flight.

## Run

Needs Python 3.9+ and `pyserial` (live input only).

```
./telemetry_bridge.py --synthetic                         # scripted fake mission, for UI development
./telemetry_bridge.py --port /dev/serial/by-id/<pocket>   # live from the Pocket
./telemetry_bridge.py --port ... --record test1.crsf      # live + save raw bytes
./telemetry_bridge.py --replay test1.crsf                 # replay a recording
# add --http 8765 to serve the stream to browsers (Server-Sent Events, see below)
# add --udp 127.0.0.1:5600 to also send each JSON object as a UDP datagram
python3 -m unittest -v                                    # decoder tests (synthetic frames)
```

Output: one JSON object per line on stdout (10 Hz by default, `--rate`).

## Browser (Server-Sent Events)

`--http 8765` serves the same JSON objects over HTTP, with CORS open (`Access-Control-Allow-Origin: *`):

| Endpoint | Returns |
|---|---|
| `GET /telemetry` | `text/event-stream`: the latest object on connect, then every new one (`data: {...}`), a keepalive comment every 15 s, `retry: 1000` |
| `GET /latest` | the latest object as plain JSON (`null` before the first publish) |

```js
const es = new EventSource("http://localhost:8765/telemetry");
es.onmessage = (e) =>
  window.dispatchEvent(new CustomEvent("vigil:telemetry", { detail: JSON.parse(e.data) }));
```

`EventSource` reconnects by itself if the bridge restarts. It binds to `127.0.0.1` by default. For a browser on another machine, add `--http-host 0.0.0.0` and allow the port through that machine's firewall (e.g. `ufw allow 8765/tcp`), then use `http://<ground-pc-ip>:8765/telemetry`.

## Synthetic mission (`--synthetic`)

A scripted ~110 s flight that loops forever and fills **every field the drone will eventually send**, including GPS, altitude and speed that the real drone only sends after M3/M4. It produces CRSF bytes, so it goes through the same decoder as live data. Every object is marked `source: "synthetic"`, and yaw is published as `yaw_reference: "relative"`.

| Time (s) | Flight mode | What happens |
|---|---|---|
| 0–12 | `WAIT` | disarmed, satellites climb 0→9, `fix_valid` false until 6, `lat`/`lon` null |
| 12–20 | `OK` | disarmed, GPS fix |
| 20–30 | `ANGL` | armed (`home` set), climbs to 10 m at 1 m/s |
| 30–54 | `AH`, `HOLD` | hovering at 10 m |
| 54–81 | `WP` | flies 40 m north, 40 m east, 20 m south at 4 m/s (up to ~55 m from home). LQ drops to 55 % (`degraded`) at 62–68 s, then **no data for 2.5 s** at 72–74.5 s (`lost`) |
| 81–102 | `RTH` | flies home and lands |
| 102–110 | `OK` | disarmed on the ground |

Battery sags under load and drains while armed (4S, from 16.6 V).

## VehicleTelemetry fields

| Field | Source | Unavailable (null) when |
|---|---|---|
| `timestamp_ms` | ground clock at publish time | never |
| `armed` | INAV flight-mode string: `OK`/`!ERR`/`WAIT` = disarmed, anything else = armed | no flight-mode frame received yet |
| `battery_v` | battery frame (pack voltage) | no battery frame yet, or below 2 V (pack not connected to the board's sense divider) |
| `roll_deg`, `pitch_deg` | attitude frame | no attitude frame yet |
| `yaw_deg` | magnetic heading, 0–360°, with `yaw_reference: "magnetic"`, while the drone reports a healthy magnetometer (frame 0x89). Otherwise `--relative-yaw` publishes INAV's yaw with `yaw_reference: "relative"` | no healthy magnetometer and no `--relative-yaw` |
| `altitude_m` | barometric-altitude frame 0x09 (INAV's estimated altitude above the boot/arming reference, 0.1 m); falls back to the GPS frame (whole metres) | neither frame received |
| `lat`, `lon` | GPS frame | no GPS frames, or `fix_valid` is false |
| `fix_valid` | **heuristic**: ≥ 6 satellites and a non-zero position (CRSF has no explicit fix flag) | no GPS frames |
| `link_state` | `no_data` / `connected` / `degraded` (uplink LQ < 70) / `lost` (no drone frames for 1.5 s) | never |

Extras (not in the shared contract; the UI may ignore them):

| Field | Meaning | Null when |
|---|---|---|
| `flight_mode` | INAV mode string: `WAIT` (no GPS), `OK`, `!ERR` (disarmed); `ANGL`, `AH` (alt hold), `HOLD` (position hold), `WP` (mission), `RTH`, `!FS!` (failsafe), … | no flight-mode frame yet |
| `battery_pct` | INAV's estimate from voltage (no current sensor) | same as `battery_v` |
| `climb_ms` | vertical speed, m/s, up positive (vario frame, else the baro-altitude frame) | neither frame yet |
| `speed_ms`, `course_deg` | GPS ground speed and course over ground | no valid fix |
| `satellites` | GPS satellite count | no GPS frames |
| `home`, `distance_home_m` | `{lat, lon}` of the first valid fix after arming (as INAV sets home), and straight-line distance from it | not armed since the bridge started, or no fix |
| `armed_time_s` | seconds since arming, measured on the ground | disarmed |
| `link` | `{uplink_lq, uplink_rssi_dbm, downlink_lq, downlink_rssi_dbm}` from ELRS | Pocket hasn't sent link stats yet |
| `data_age_ms` | time since the last frame from the drone | nothing received yet |
| `source` | `pocket` / `replay` / `synthetic` | never |
| `yaw_reference` | `"magnetic"` (healthy magnetometer) or `"relative"` (`--relative-yaw`); only present when `yaw_deg` is | (absent) |
| `imu` | `{accel_g: [x, y, z], gyro_dps: [x, y, z]}`: accelerometer in g and gyro in °/s, board axes after alignment (frame 0x88) | firmware without patch 0010 |
| `mag` | `{field_counts: [x, y, z], heading_deg, healthy}`: INAV's calibrated magnetometer counts (not a physical unit), its heading, and whether the magnetometer is detected and healthy (frame 0x89) | no magnetometer detected, or firmware without patch 0010 |

Values persist after a link loss; check `link_state` and `data_age_ms`. Not available from this drone at all (no sensor or not sent over CRSF): battery current and mAh used, temperature.

### Ground-telemetry firmware (branch `ground-telemetry`)

That branch builds firmware that **can never arm** (patch 0007; status shows `KILLSWITCH`) and streams everything while sitting on the ground: attitude, flight mode, GPS (NMEA driver restored, patch 0009), barometric altitude, IMU and magnetometer (patch 0010). Frames 0x88/0x89 are custom extended CRSF frames (destination 0xEA, origin 0xC8, then the payload); 0x09 uses the standard Betaflight/EdgeTX packing, so the Pocket's own telemetry screen can show the altitude too. Every frame type is sent at about 10 Hz; with a low ELRS telemetry ratio some updates are dropped, so set the ratio to 1:2 in the ELRS Lua script if the stream looks slow.

## Pocket setup (G0)

1. **ELRS telemetry on:** on the Pocket, SYS → Tools → ExpressLRS → *Telem Ratio* **`1:2`** at 250 Hz. Measured 2026-10-10: about 14 Hz each for attitude, battery and flight mode (the default ratio gave only 0.2 Hz).
2. **USB serial output:** SYS → Hardware → serial port **USB-VCP** → mode **Telemetry Mirror**. Menu names vary between EdgeTX versions; check on the radio.
3. Plug the Pocket into the ground computer and choose **USB Serial (VCP)** at the USB prompt (not Joystick or Storage).
4. Find the port: `ls -l /dev/serial/by-id/`. The flight controller is `usb-INAV_REDSTART…`, and the Pocket is the other entry. Both use the same STM32 VID:PID, so go by name, not number.

**G0 passes when** the drone is powered (props off) and `--port` output shows `link_state: connected`, with `roll_deg`/`pitch_deg` following when you tilt the drone. Record one session with `--record` so the UI team has real data to replay.
