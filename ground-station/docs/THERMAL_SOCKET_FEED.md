# Live thermal feed

From `ground-station`, start the dashboard with `npm run dev` and, in a second terminal, run:

```powershell
npm run thermal:relay
```

From the repository root, run the AI camera process:

```powershell
python -m AI.scripts.lepton_live --socket-url http://127.0.0.1:5000
```

Connect the ground computer to the Lepton-Camera Wi-Fi first. The AI process is the Socket.IO client; the relay receives and broadcasts its events to the browser. The dashboard connects automatically. Pin testing pauses its live connection to keep camera data separate from fixtures.

The relay binds to `127.0.0.1:5000` by default, accepts the dashboard origins `http://127.0.0.1:5173` and `http://localhost:5173`, and permits the Python client's origin-free connection. It permits one publishing connection at a time. Closing that publisher releases the slot. This is a local ground-computer service, without network authentication.

## Data handling

- `vigil:frame`: native 160 × 120 grayscale PNG data URL, opaque `frame_id`, and ground-computer `capture_timestamp_ms`.
- `vigil:detection`: same frame ID and timestamp, inference time, and `persons` array.
- Frames and detections are paired before being dispatched to the existing dashboard listeners. Either arrival order works; unmatched entries are bounded to 32 per event type. Older completed pairs and timestamp mismatches are discarded.
- Person boxes must be normalized, finite, and have positive dimensions. Invalid people are dropped individually. Empty person arrays clear overlays and map pins.
- Track IDs become strings; null track IDs and null temperatures are omitted. The supplied bottom-center must agree with the bounding-box foot midpoint used by the current projection. Feet marked obscured or touching the bottom edge are withheld from geolocation.
- Center temperatures are nominal camera readings, not calibrated core/body temperatures. This adapter does not assign medical high/low categories.
- The existing two-second stale-feed rule withholds locations after camera packets stop. Reconnect clears pending pairs. No frames are persisted by the relay.

Map pins still require live drone telemetry with a GPS fix, a valid north heading, and the location settings/ground elevation. `capture_timestamp_ms` is arrival time on the ground computer, rather than sensor exposure time; camera/network latency remains a projection uncertainty. The adapter does not change camera geometry or the shared 5.1-second elevation request limit.

## Configuration

Client defaults can be overridden in `.env.local` (restart Next.js; public variables are baked into production builds):

```dotenv
NEXT_PUBLIC_THERMAL_SOCKET_URL=http://127.0.0.1:5000
NEXT_PUBLIC_THERMAL_SOCKET_NAMESPACE=/
NEXT_PUBLIC_THERMAL_FRAME_EVENT=vigil:frame
NEXT_PUBLIC_THERMAL_DETECTION_EVENT=vigil:detection
```

The relay reads environment variables from its launching terminal. Set `THERMAL_RELAY_PORT`, `THERMAL_RELAY_HOST`, `THERMAL_RELAY_ORIGINS` (comma-separated browser origins), and the same namespace/event variables there if changing defaults. Match the AI's `--socket-namespace`, `--frame-event`, and `--detection-event`. An external browser needs a relay URL reachable from that browser and its exact origin allowed. Do not expose this unauthenticated relay to an untrusted network.

For production, run `npm run thermal:relay` alongside the Next.js server. This separate process keeps Socket.IO out of request-scoped Next.js route handlers.

`npm test` includes adapter and real Socket.IO publisher-to-browser relay tests. Hardware testing requires the camera and AI environment.

References: [Socket.IO initialization](https://socket.io/docs/v4/server-initialization/), [client options](https://socket.io/docs/v4/client-options/), [server options](https://socket.io/docs/v4/server-options/).
