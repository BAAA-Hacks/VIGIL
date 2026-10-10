# Ground telemetry bridge

```
drone (INAV, CRSF telemetry) → RP1 → ELRS → Pocket (EdgeTX) → USB serial → telemetry_bridge.py → VehicleTelemetry JSON → UI
```

Downlink only for now. Nothing on the drone depends on this link: unplugging the Pocket's USB or killing the script changes nothing in flight.

## Run

Needs Python 3.9+ and `pyserial` (live input only).

```
./telemetry_bridge.py --synthetic                         # fake drone, for UI development
./telemetry_bridge.py --port /dev/serial/by-id/<pocket>   # live from the Pocket
./telemetry_bridge.py --port ... --record test1.crsf      # live + save raw bytes
./telemetry_bridge.py --replay test1.crsf                 # replay a recording
# add --udp 127.0.0.1:5600 to also send each JSON object as a UDP datagram
python3 -m unittest -v                                    # decoder tests (synthetic frames)
```

Output: one JSON object per line on stdout (10 Hz by default, `--rate`).

## VehicleTelemetry fields

| Field | Source | Unavailable (null) when |
|---|---|---|
| `timestamp_ms` | ground clock at publish time | never |
| `armed` | INAV flight-mode string: `OK`/`!ERR`/`WAIT` = disarmed, anything else = armed | no flight-mode frame received yet |
| `battery_v` | battery frame (pack voltage) | no battery frame yet |
| `roll_deg`, `pitch_deg` | attitude frame | no attitude frame yet |
| `yaw_deg` | **null by design**: no compass, so yaw has no north reference. `--relative-yaw` publishes it with `yaw_reference: "relative"` | always (unless flag) |
| `altitude_m` | GPS frame (INAV's estimated altitude above home) | before GPS is enabled (M4) |
| `lat`, `lon` | GPS frame | no GPS frames, or `fix_valid` is false |
| `fix_valid` | **heuristic**: ≥ 6 satellites and a non-zero position (CRSF has no explicit fix flag) | no GPS frames |
| `link_state` | `no_data` / `connected` / `degraded` (uplink LQ < 70) / `lost` (no drone frames for 1.5 s) | never |

Extras the UI may ignore: `flight_mode`, `climb_ms`, `satellites`, `link{uplink_lq, uplink_rssi_dbm, downlink_lq, downlink_rssi_dbm}`, `data_age_ms`, `source` (`pocket` / `replay` / `synthetic`). Values persist after a link loss; check `link_state` and `data_age_ms`.

## Pocket setup (G0)

1. **ELRS telemetry on:** on the Pocket, SYS → Tools → ExpressLRS → *Telem Ratio* **`1:2`** at 250 Hz. Measured 2026-10-10: about 14 Hz each for attitude, battery and flight mode (the default ratio gave only 0.2 Hz).
2. **USB serial output:** SYS → Hardware → serial port **USB-VCP** → mode **Telemetry Mirror**. Menu names vary between EdgeTX versions; check on the radio.
3. Plug the Pocket into the ground computer and choose **USB Serial (VCP)** at the USB prompt (not Joystick or Storage).
4. Find the port: `ls -l /dev/serial/by-id/`. The flight controller is `usb-INAV_REDSTART…`, and the Pocket is the other entry. Both use the same STM32 VID:PID, so go by name, not number.

**G0 passes when** the drone is powered (props off) and `--port` output shows `link_state: connected`, with `roll_deg`/`pitch_deg` following when you tilt the drone. Record one session with `--record` so the UI team has real data to replay.
