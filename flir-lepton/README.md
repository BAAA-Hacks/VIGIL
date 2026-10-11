# Lepton thermal streamer (XIAO ESP32-S3)

Firmware that reads a FLIR Lepton 3.5 over VoSPI and streams it over Wi-Fi from a standalone
access point. No router or internet needed.

- **AP:** `Lepton-Camera`, camera at `http://192.168.4.1/`. The password is set in `include/secrets.h` (gitignored); copy `include/secrets.example.h` to create it before the first build.
- **Driver:** vendored and patched from [ducky64/arduino-lepton](https://github.com/ducky64/arduino-lepton)
  (`lib/arduino-lepton/`, changes listed in `PATCHES.md`). JPEG encoding uses
  [JPEGENC](https://github.com/bitbank2/JPEGENC).

**Status (2026-10-10):**
- **Capture:** verified on hardware (Lepton 3.5, serial 22856917). About 8.78 FPS with VSYNC on at 20 MHz SPI, with no invalid frames, resyncs or resets.
- **Wi-Fi:** the AP, web page, MJPEG and `/raw` endpoints are not yet tested from a client.

## Wiring

| Lepton breakout (V2.0) | XIAO ESP32-S3 | GPIO |
|---|---|---|
| SDA | D4 | 5 |
| SCL | D5 | 6 |
| SPI_CLK | D8 | 7 |
| SPI_MISO | D9 | 8 |
| SPI_CS | D3 | 4 |
| VSYNC (Lepton GPIO3) | D2 | 3 |
| RESET_L | D1 | 2 |
| GND | GND | |

- **Power:** the breakout gets its own 3–5.5 V on J3 and shares ground with the XIAO.
- **Unconnected pins:** MOSI and PWR_DWN_L aren't connected; the breakout holds PWR_DWN_L high.
- **Pins in `include/config.h`:** they match the XIAO variant's `pins_arduino.h`, so D8/D9 are the board's default SPI SCK/MISO.
- **D2 / GPIO3:** this is an ESP32-S3 strapping pin, but it's only sampled at reset, so it's safe to use for VSYNC.

## Build and upload

```bash
cd flir-lepton
pio run                               # build
pio run -t upload                     # flash over USB-C (ttyACM*)
pio device monitor                    # serial log, 115200
```

- **Bootloader mode:** if upload can't find the board, hold **BOOT**, tap **RESET**, release BOOT, then retry.
- **Permissions on Arch:** `/dev/ttyACM*` belongs to the `uucp` group. If you get "permission denied", either add yourself to `uucp` (`sudo usermod -aG uucp $USER`, then log in again) or install PlatformIO's udev rules.

## Expected serial output

```
[I][main.cpp] Lepton streamer starting, chip ESP32-S3 rev 0, 240 MHz
[I][main.cpp] PSRAM: 8388608 bytes
[I][main.cpp] I2C scan: Lepton (0x2A) found          # "not responding yet" is OK right at power-up
[I][StreamServer.cpp] AP 'Lepton-Camera' up at 192.168.4.1
[I][LeptonCamera.cpp] resetting Lepton
[I][LeptonCamera.cpp] Lepton ready after ~1–5 s
[I][LeptonCamera.cpp] serial ..., part '500-0771-01...', software ...
[I][LeptonCamera.cpp] configured: Raw14/TLinear, VSYNC on, SPI 20000000 Hz
[I][main.cpp] streaming fps=8.78 frames=46 (+9) invalid=0 resyncs=0 outOfPhase=0 resets=0 vsyncTimeouts=0
              packets=30997 discardPkts=8428 discardSegs=549 hdr=0014527e heap=150796 ...
```

The 1 Hz status line reports the following:

| Field | Meaning |
|---|---|
| `fps` | Real unique frames from the last ~2 s. Duplicates are never counted. Expect ~8.7. |
| `invalid` | Frames abandoned after data started arriving. |
| `resyncs` | VoSPI sync losses. Each one costs 185 ms with CS held high. |
| `outOfPhase` | A read started mid-frame and was dropped quietly. A few are normal. |
| `resets` | Hardware resets of the camera after 3 s with no frame. |
| `vsyncTimeouts` | No VSYNC pulse within 20 ms; the firmware then polls instead. |
| `packets` / `discardPkts` / `hdr` | VoSPI packets read, how many were discards, and the last packet header. If every packet is a discard and `hdr` stays `0fff....`, SPI works but no segment ever starts. `ffffffff` means MISO is floating. |
| `discardSegs` | Non-unique (ttt=0) segments. Normal: Lepton 3.x sends 2 of every 3 frames as these. |

A one-second `+0` shortly after start-up is the camera's automatic flat-field correction.

## HTTP endpoints

| Endpoint | Returns |
|---|---|
| `GET /` | Debug viewer: live stream, FPS/status, palette, rotation, mirror. |
| `GET /stream` | MJPEG, `multipart/x-mixed-replace; boundary=frame`. Each part has `X-Frame-Id` and `X-Timestamp-Ms` headers. Up to 3 clients. |
| `GET /capture` | One JPEG of the latest complete frame, with `X-Frame-Id` and `X-Timestamp-Ms`. Returns 503 before the first frame. |
| `GET /raw` | Binary stream of raw 16-bit frames for the ground-station adapter (format below). 1 client. |
| `GET /status` | JSON: `cameraInit`, `cameraState`, `framesCaptured`, `framesInvalid`, `resyncs`, `outOfPhase`, `resets`, `fps`, `freeHeap`, `freePsram`, `streamClients`, `rawClients`, `apIp`, `uptimeMs`. |
| `GET /settings?palette=gray\|iron\|rainbow&rotation=0\|90\|180\|270&mirror=0\|1` | Changes the JPEG output for all clients and returns the settings as JSON. Call it with no arguments to read them. |

- **CORS:** every response carries `Access-Control-Allow-Origin: *`.
- **What the settings affect:** they change the JPEG output only, never `/raw`.

### `/raw` record format

The HTTP header is followed by back-to-back fixed-size records (38,424 B each), one per captured
frame. All fields are little-endian:

| Offset | Type | Field |
|---|---|---|
| 0 | char[4] | magic `LEP1` |
| 4 | u32 | frame ID (capture sequence, same as `X-Frame-Id`) |
| 8 | u32 | timestamp, ms since ESP32 boot |
| 12 | u16 | width (160) |
| 14 | u16 | height (120) |
| 16 | u16 | min raw value in this frame |
| 18 | u16 | max raw value in this frame |
| 20 | u32 | flags: bit 0 = TLinear mode requested |
| 24 | u16[19200] | pixels, row-major, unrotated |

- **Gaps:** a slow reader skips frames rather than delaying capture. Gaps in the frame ID show how many were skipped.
- **Units:** pixel values are the camera's raw output. With TLinear on they are *nominally* kelvin × 100, but this firmware doesn't calibrate or validate temperatures, so treat them as relative intensities.

`tools/lepton_raw.py` is a standard-library-only reader that prints FPS and gaps and can save
PGM snapshots. It's the starting point for the ground-station adapter:

```bash
python3 tools/lepton_raw.py                       # stats once per second
python3 tools/lepton_raw.py --save 5 --out frames # also save 5 frames as PGM
```

## How it works

- **Capture task (core 1, priority 23):**
  - Waits for VSYNC (falling back to polling after 20 ms), then reads VoSPI segments through the patched driver.
  - Puts each complete 4-segment frame into a triple buffer. It never waits on readers.
  - Rebuilds and reconfigures the camera if no frame arrives for 3 s.
- **Stream task (core 0):**
  - Takes the newest frame and runs min/max contrast, palette, rotation and mirror (`ThermalProcessor`).
  - JPEG-encodes it only when an MJPEG or capture client needs it, then pushes it to clients.
  - Slow clients skip frames. A client that accepts nothing for 5 s, or fails mid-part, is dropped.
- **HTTP task (core 0):** Arduino `WebServer`. It only parses requests and hands stream sockets to the stream task.

Settings such as the SPI clock, VSYNC use, timeouts and client limits are in `include/config.h`.

## Troubleshooting

- **`Lepton not ready` / I²C errors:**
  - Check SDA/SCL, the shared ground, and J3 power.
  - The breakout must have I²C pull-ups. Fit 2.2–4.7 kΩ to 3.3 V on SDA and SCL if they're missing.
- **Frequent `resyncs`, or `fps` stuck at 0 while state is `streaming`:**
  - Set `SPI_CLOCK_HZ` to 16000000 and check SCK/MISO/CS wiring length (keep it short).
  - Try `USE_VSYNC = false` to rule out the VSYNC line.
- **`vsyncTimeouts` climbing every second:** VSYNC isn't reaching D2. Capture still works by polling, just less efficiently.
- **Stream stops but `/status` still works:** the browser `<img>` reconnects by itself after 1 s; check `resets` in the log.
