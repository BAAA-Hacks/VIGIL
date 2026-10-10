# VIGIL Ground Station

Next.js App Router + TypeScript + React dashboard with Tailwind CSS v4 for thermal imagery and human detections. All initial imagery, detections, and timing are explicitly simulated. Flight telemetry is unavailable until connected.

## Run

    npm install
    npm run dev

Active dashboard: src/components/mission/MissionDashboard.tsx. Route: src/app/page.tsx. Component styling uses Tailwind utilities in TSX. The UI palette contains exactly six base CSS variables under :root in src/app/globals.css: paper (#FAFAF7), ink (#474647), blue (#86BBD8), pink (#FF1053), yellow (#FFF07C), and peach (#FF9370). Tailwind opacity modifiers handle tints and borders; shadows and gradients use the same base colors with transparency. Keep future styling within these six colors. The dashboard uses off-white surfaces and charcoal text, with blue low-temperature indicators, peach/pink high-temperature indicators, and charcoal navigation and map controls.

## Verify / production build

    npm run build

## Demo

Use Feed controls to choose Human detected, No target, or Disconnected feed. Pause stops frames; after 2 seconds results become stale and after 5 seconds the feed is disconnected. Overlays can be toggled and the image enlarged. Layout adapts to mobile screens.

## Live integration

The live thermal adapter connects automatically to the local relay. Start it in a second terminal with `npm run thermal:relay`, then launch the AI process with `--socket-url http://127.0.0.1:5000`. See [Live thermal feed](docs/THERMAL_SOCKET_FEED.md) for complete setup. The app also listens for browser CustomEvents:

```js
window.dispatchEvent(new CustomEvent('vigil:frame', { detail: {
  frame_id: 'frame-1', timestamp_ms: Date.now(), width: 160, height: 120,
  pixel_format: 'encoded-image', payload: 'data:image/png;base64,...'
}}));
window.dispatchEvent(new CustomEvent('vigil:detection', { detail: {
  frame_id: 'frame-1', processing_ms: 38,
  detections: [{ class: 'Human', confidence: 0.94, bbox_xyxy_norm: [0.43, 0.28, 0.56, 0.79] }]
}}));
```

The camera/backend adapter must convert raw thermal samples to an encoded image data URL. Coordinates are normalized 0–1, top-left origin. Events must carry matching frame IDs; mismatched results are withheld. Invalid bounding boxes are rejected. Send an empty detections array to report no target. Live palettes are supplied by the backend; palette controls apply only to simulation. The dashboard now receives the Lepton AI producer through the local Socket.IO relay. See [Live thermal feed](docs/THERMAL_SOCKET_FEED.md) for startup and the producer contract. Mission upload is documented separately in [INAV shape missions](docs/INAV_SHAPE_MISSIONS.md).



## Source structure

- `src/components/mission/`: the mission page (map, thermal viewer, pins, drone info, location settings).
- `src/hooks/`: telemetry SSE (`useVehicleTelemetry`), pin-test replay (`usePinTest`), and the live adapter (`usePersonLocations`).
- `src/lib/events.ts`: `vigil:*` event names and the typed `dispatchVigil` helper.
- `src/lib/locationSnapshot.ts`, `geolocation.ts`, `terrainGrid.ts`: pure person-location projection.
- `src/lib/personMapController.ts`, `smoothMapZoom.ts`: Leaflet map ownership and zoom.
- `src/lib/thermalSimulation.ts`: canvas scene generation and palettes.
- `src/lib/validation.ts`: validation of external event payloads.
- `src/types/vigil.ts`: shared domain types.
- `tests/`: regression tests for validation, simulation, projection, pin-test and drone readings.

Run `npm test`, `npm run typecheck`, and `npm run build` to verify changes. Run `npm run format` to format source and tests. Tests use Node 22's TypeScript stripping support.

### Active mission page

The current `/` page renders `src/components/mission/MissionDashboard.tsx`, composing `MissionHeader`, `MapArea`, `DroneInfoPanel`, `PinsPanel`, and `TestDataToggle`. `MissionPanel` shares the panel frame; `PersonPin` owns each person row and its details; `ViewerPane` shares main/inset placement and promotion controls; `MapViewSelect` defines the typed map options. Drone reading formatting lives in `src/lib/droneReadings.ts`. `StatBox` is reusable and declared outside the parent render. Pins and telemetry are passed as typed props; mock values are stored in `src/data/missionDemo.ts` and their types in `src/types/mission.ts`. Scrollbar styling uses Tailwind utilities with root color variables.

### Person map and view switching

Person records include numeric latitude and longitude in addition to their displayed coordinates. `PersonMap` uses Leaflet with selectable Esri street, topographic, and satellite tiles, renders all person markers, and synchronizes marker clicks with the person list. List selection centers the map and opens the coordinate popup. `MapArea` switches map and simulated thermal imagery between the main view and inset without unmounting the map; a ResizeObserver updates its dimensions. Clicking the thermal inset, the map inset expand badge, or the Swap views control switches views. The map supports mouse-wheel and trackpad zoom plus touch pinch zoom; the map inset expand badge leaves the map surface interactive. Live thermal frames and detections use the Socket.IO adapter; geolocation requires synchronized drone telemetry and configured altitude/heading conventions.

### Local dummy data

`src/data/dummy-data.example.json` is the committed fixture for 10 people and the pin-test replay (`pin_test`), so a fresh checkout builds and tests without extra files. To use different local data, put a file with the same shape at the gitignored `src/data/dummy-data.json`; `next.config.mjs` then aliases the example import to it for `dev` and `build` (restart the dev server after adding or removing it). Tests always use the committed example. Both are read through `src/data/fixture.ts`. The fixture stores numeric coordinates and Celsius temperatures; `missionDemo.ts` converts these values into display strings. Person statuses are explicit demo labels; temperature is a simulated central reading. The current UI shows person temperatures in Fahrenheit and PCB temperature in Celsius.

Ground elevation: opening a person dropdown queries /api/elevation, which sends the selected latitude and longitude to USGS EPQS. Successful upstream requests are cached for 24 hours. No-data and service failures show Unavailable with a retry control. Ground elevation is distinct from drone altitude.

## Synthetic telemetry bridge
The dashboard's /api/telemetry SSE route runs python ../flight-controller/ground/telemetry_bridge.py --synthetic and forwards validated JSON lines to the browser. Python must be on PATH; PYTHON_EXECUTABLE can select an alternative interpreter. Each browser connection owns its process, stopped when the connection closes. This is local synthetic testing, not a live serial connection. The supplied simulator has no GPS, altitude, climb, or absolute yaw output; these display Unavailable. Ground speed, distance from home, and PCB temperature are absent from the contract and display Not supplied. Flight time is calculated from received packets as described below. Person records remain dummy data.

Synthetic telemetry starts stopped. Use Start test / Stop test in the bottom right. Stopping closes the stream and terminates its Python process. Flight time measures elapsed time from the first valid received packet in the current session, regardless of arming. A two-second packet gap, connection error, or Stop resets it to 00:00. The next packet begins a new session.

Elevation API requests share a server-wide gate with at least 5.1 seconds between request starts, including failed requests. Answers (including no-coverage) are cached in-process for 24 hours per coordinate rounded to 5 decimals, so repeat lookups skip the gate, and the response carries a 24-hour private Cache-Control. This applies to the single local server process; separate server processes would need a shared limiter. Camera defaults are in src/lib/cameraConfig.ts: FLIR Lepton 3.5, forward, 20 degrees down from horizontal, 160x120, nominal 57-degree horizontal / 71-degree diagonal FOV. FLIR specifies less than 13% optical distortion; accurate pixel-to-ray projection requires measured intrinsics and distortion coefficients. The ideal square-pixel pinhole estimate (44.3-degree vertical / 68.3-degree diagonal) is only an approximation, not a replacement for the manufacturer specifications. Source: https://flir.netx.net/file/asset/13333/original/attachment/ (Rev 400, Table 1). Person geolocation still requires takeoff-reference capture and an agreed north-referenced heading estimate; relative yaw is not silently treated as absolute heading.


## Person coordinate estimates

The mission dashboard now projects the bottom center of each matched human/person bounding box through a provisional Lepton 3.5 pinhole model (160×120, horizontal FOV 57°, 20° forward/down mount). The published diagonal FOV 71° is retained in cameraConfig; it is not used to invent a distortion correction. Results remain estimates until thermal intrinsics, distortion, mounting and surveyed target error have been measured.

**Altitude clarification (October 10): altitude_m is sea-level elevation, not takeoff-relative height.** UI configuration uses absolute altitude and subtracts reference ground elevation. Confirm the drone and terrain vertical datums before applying. Camera offset from the telemetry reference defaults to zero. The initial valid drone coordinates are sent once to the existing elevation route; Refresh reference ground explicitly replaces the reference. USGS calls share the existing 5.1-second gate with selected-person lookups. No automatic terrain grid is fetched.

Open Location settings in Marked locations, verify the reference ground, clock and physical conventions, and apply. Enter a known yaw-to-north offset, or enable forward-flight calibration. Automatic calibration needs at least three stable GPS-course observations separated by 2 seconds, each moving at least 10 m; it rejects turns, steep attitude, stale fixes and stationary data. Wind/sideslip still introduce heading error. Calibrations expire after 15 seconds without qualifying observations.

### Live adapter contract

- Dispatch vigil:telemetry with the existing VehicleTelemetry object. The current test-data SSE is also accepted. Synthetic bridge packets presently omit GPS/yaw/altitude and cannot generate coordinates; no missing values are fabricated.
- Dispatch vigil:frame with ThermalFrame, a unique frame_id, timestamp_ms in the telemetry clock (or supply frameClockOffsetMs), width 160, height 120, and a data:image payload. Dispatch vigil:detection with the same frame_id and normalized bbox_xyxy_norm. Either arrival order works within the 32-frame buffer. Feed clocks must remain monotonic within a session.
- Detection may include track_id (stable identity from the tracker), feet_visible (false withholds projection), temperature_c and temperature_status (normal/elevated/low supplied by the detector). Missing temperature is unavailable; no medical temperature classification is inferred. Without track_id each frame receives distinct detection IDs.
- Configuration can also be dispatched as vigil:location-config with LocationConfig from src/lib/geolocation.ts. Applying settings resets timing/heading history. UI uses altitudeReference absolute; the pure engine also supports takeoff-relative replay fixtures. takeoffElevationM is the reference ground elevation field in either mode.
- Optional vigil:terrain carries TerrainGrid from src/lib/terrainGrid.ts: south/west, positive latitudeStep/longitudeStep, elevation rows south-to-north, columns west-to-east. All elevations must share the altitude datum. Send null to clear. The grid is local; it causes no external requests. Outside coverage or null cells withhold locations. The solver samples at 5 m along the ray then bisects the first sampled crossing; features narrower than a sampling step can be missed. Supply sufficiently detailed terrain for the intended area.

Telemetry is bracketed at capture time (maximum 500 ms bracket, no extrapolation), angle wrap is handled, and link gaps invalidate course calibration. Frames or telemetry older than 2 seconds by arrival are withheld. Rays within 3° of the horizon, clipped boxes, invalid fixes/heights or ranges over 2 km are rejected. Geographic offsets use WGS84 local curvature, supported within 2 km and latitudes below 85°. Roll/pitch interpolation assumes small changes between adjacent packets; synchronize and measure transport latency before field use.

Live estimates replace fixture pins after the first real frame, preserve map zoom during updates, and expose unavailable reasons. Selection still centers the map; thermal/map swapping and layer selection remain available. Local-grid support is an estimate too; this implementation has mathematical fixture tests, not measured rescue-location accuracy.

Selected-person USGS lookup coordinates are frozen when its details open. Tracking updates do not request EPQS for every video frame. Close and reopen to query the updated selected position. Applying a new location configuration clears any local terrain grid; dispatch the compatible grid afterward.

## Testing calculated pins

Use **Test pins** at the bottom right to replay complete ELRS-format telemetry plus native 160×120 Wi-Fi-format thermal frames and ten tracked person detections at 5 Hz. Stop pin test clears the replay and restores the existing location configuration. Start test still runs the original Python bridge; the two test sources are mutually exclusive.

All replay values are under pin_test in the demo fixture (src/data/dummy-data.example.json, or a local dummy-data.json override). The fixture drone is at 34.0525, -118.243, 510 m above sea level, with 500 m local flat terrain (10 m above ground), a 20° camera mount, zero roll/pitch/yaw and known north offset. No person coordinates are supplied to the replay: pins are projected from box bottoms. Frame IDs/capture timestamps are renewed together on each tick. The thermal image silhouettes use those same boxes. Fixture terrain avoids USGS queries during playback/selection.

A blue square D pin marks fresh valid drone GPS, with coordinates and sea-level altitude in its popup. Person pins remain numbered circles. Stale/invalid drone positions are removed. Test imagery and temperature labels are synthetic, not camera measurements.


Drone telemetry extras speed_ms, course_deg, distance_home_m, pcb_temp_c, battery_pct and home are optional and validated. The dashboard displays bridge-provided speed/course/distance/PCB temperature; unsupported live sensors remain unavailable. Roll and pitch display in signed degrees. The pin test models a steady 10 m hover (0 m/s, 0 m from home, 0.4° roll, -0.6° pitch, HOLD, PCB 38.5°C). The Python synthetic mission retains its CRSF decoder path but now uses slow, small attitude changes and a synthetic-only PCB warmup (38–43°C).

Start test launches the synthetic bridge with --relative-yaw so its yaw reading is available and explicitly labelled relative. Stop/restart any running test stream to load generator changes.
