# VIGIL Ground Station

Next.js App Router + TypeScript + React dashboard with Tailwind CSS v4 for thermal imagery and human detections. All initial imagery, detections, and timing are explicitly simulated. Flight telemetry is unavailable until connected.

## Run

    npm install
    npm run dev

Dashboard component: src/components/Dashboard.tsx. Route: src/app/page.tsx. Global thermal styles: src/app/globals.css. Tailwind utilities handle layout and primary actions. Custom CSS preserves the detailed thermal visualization.

## Verify / production build

    npm run build

## Demo

Use Feed controls to choose Human detected, No target, or Disconnected feed. Pause stops frames; after 2 seconds results become stale and after 5 seconds the feed is disconnected. Overlays can be toggled and the image enlarged. Layout adapts to mobile screens.

## Live integration

Select Live integration. The app listens for browser CustomEvents:

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

The camera/backend adapter must convert raw thermal samples to an encoded image data URL. Coordinates are normalized 0–1, top-left origin. Events must carry matching frame IDs; mismatched results are withheld. Invalid bounding boxes are rejected. Send an empty detections array to report no target. Live palettes are supplied by the backend; palette controls apply only to simulation. No network transport or flight control is implemented.



## Source structure

- `src/components/Dashboard.tsx`: assembles the dashboard and owns display preferences.
- `src/components/dashboard/`: sidebar, header, metrics, thermal panel/image, detection overlay/insight, and feed controls.
- `src/hooks/useVigilFeed.ts`: demo timer, external event subscriptions, feed lifecycle, and cleanup.
- `src/lib/demoFeed.ts`: reproducible demo frames and detections.
- `src/lib/feedStatus.ts`: frame matching, freshness, and status calculations.
- `src/lib/thermalSimulation.ts`: canvas scene generation and palettes.
- `src/lib/validation.ts`: validation of external event payloads.
- `src/types/vigil.ts`: shared domain types.
- `tests/vigil.test.ts`: regression tests for integration rules and simulation.

Run `npm test`, `npm run typecheck`, and `npm run build` to verify changes. Run `npm run format` to format source and tests. Tests use Node 22's TypeScript stripping support.

### Active mission page

The current `/` page renders `src/components/mission/MissionDashboard.tsx`, composing `MissionHeader`, `MapArea`, `ThermalPreview`, `DroneInfoPanel`, and `PinsPanel`. `StatBox` is reusable and declared outside the parent render. Pins and telemetry are passed as typed props; mock values are stored in `src/data/missionDemo.ts` and their types in `src/types/mission.ts`. Scrollbar styles live in the global stylesheet. The original thermal dashboard remains available as `src/components/Dashboard.tsx` but is not mounted by the active route.

### Person map and view switching

Person records include numeric latitude and longitude in addition to their displayed coordinates. `PersonMap` uses Leaflet with Esri street tiles, renders all person markers, and synchronizes marker clicks with the person list. List selection centers the map and opens the coordinate popup. `MapArea` switches map and simulated thermal imagery between the main view and inset without unmounting the map; a ResizeObserver updates its dimensions. Clicking either inset or the Swap views control switches views. Live geolocation and thermal data remain future integrations.
