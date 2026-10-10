# VIGIL thermal-camera and detection input requirements

This document describes the current ground-station input contract. It separates camera output, detector output, and drone telemetry so the camera integration can supply everything needed for the viewer, person pins, tracking, and temperature indicators.

## Is the bottom of the bounding box enough?

The projection uses the **bottom-center of the person bounding box** as an approximation of the person's contact with the ground. That point alone is insufficient: it must be associated with a particular image capture and the drone's position and attitude at that same time.

Send the full bounding box. The app uses it for both the overlay and location calculation, and checks whether the box touches the image boundaries. If feet are obscured, the location is withheld when `feet_visible` is `false`.

## Camera/frame input

| Field | Requirement | Purpose |
| --- | --- | --- |
| `frame_id` | String identifying one capture; use a new ID for each frame | Associates the image with its detections |
| `timestamp_ms` | Finite capture timestamp in milliseconds | Matches drone GPS and attitude at capture time |
| `width` | `160` for person projection | Native sensor coordinate system |
| `height` | `120` for person projection | Native sensor coordinate system |
| `payload` | Image data URL, such as `data:image/png;base64,...` | Current browser event adapter requires this for the viewer |
| `pixel_format` | Optional descriptive string | Documents the displayed image encoding |

The current frame validator requires an image data URL. A raw radiometric array or a video URL needs conversion/adaptation before it can be passed to this adapter. Base64 is the current application contract, not a required camera transport format.

Example frame packet; replace the abbreviated payload with a real encoded image:

```json
{
  "frame_id": "thermal-000123",
  "timestamp_ms": 1791625192887,
  "width": 160,
  "height": 120,
  "pixel_format": "png",
  "payload": "data:image/png;base64,..."
}
```

Keep the native image orientation unchanged: origin at top-left, x increases right, y increases down. Do not crop, rotate, mirror, or letterbox the detector's coordinate image. If detection uses a resized image, convert its boxes back to the native sensor coordinates before sending them.

## Detector input

The detection service supplies the boxes and tracking IDs. These are not produced by the camera image stream alone.

| Field | Requirement | Purpose |
| --- | --- | --- |
| `frame_id` | Exactly matches the analyzed frame | Prevents pairing detections with a different image |
| `processing_ms` | Finite nonnegative number | Required by the current detection packet validator |
| `detections` | Array, including an empty array when nobody is detected | Clears previous results and represents this capture |
| `class` | `"person"` or `"human"`, lowercase | Current projection accepts these two classes |
| `confidence` | Number from 0 to 1 | Required detection metadata; no confidence cutoff is currently applied by projection |
| `bbox_xyxy_norm` | `[left, top, right, bottom]`, each from 0 to 1 | Draws the box and supplies the ground-contact ray |
| `track_id` | Recommended stable nonempty string, maximum 64 characters | Keeps a person's pin identity across captures |
| `feet_visible` | Recommended explicit boolean | `false` withholds that detection's coordinates; omission currently allows projection |
| `temperature_c` | Optional finite temperature in °C | Displays the temperature supplied by the thermal processing service |
| `temperature_status` | Optional `"normal"`, `"low"`, or `"elevated"` | Supplies the indicator; omission currently displays unknown status |

Without `track_id`, the app assigns a frame-specific detection ID, so stable tracking and selection across frames are unavailable.

Example detection packet without a temperature measurement:

```json
{
  "frame_id": "thermal-000123",
  "processing_ms": 24,
  "detections": [
    {
      "track_id": "person-07",
      "class": "person",
      "confidence": 0.94,
      "bbox_xyxy_norm": [0.35, 0.25, 0.48, 0.80],
      "feet_visible": true
    }
  ]
}
```

Normalize pixel-edge coordinates by image size:

```text
left   = left_pixel_edge / 160
right  = right_pixel_edge / 160
top    = top_pixel_edge / 120
bottom = bottom_pixel_edge / 120

ground_contact_x = (left + right) / 2
ground_contact_y = bottom
```

The app converts those normalized edge coordinates to sensor pixel-center coordinates internally. Do not apply an additional half-pixel correction upstream. The current projection rejects boxes with `left <= 0`, `top <= 0`, `right >= 1`, or `bottom >= 0.99`.

## Temperature measurements

Keep radiometric measurements separate from the display image. A grayscale or colored preview and a bounding box do not supply calibrated temperature values. The thermal processing service should derive `temperature_c` from the radiometric measurement corresponding to the person in that same frame.

Before integration, agree on:

- The region measured, such as a selected skin region or a person region with background excluded.
- The statistic reported, such as median, mean, or maximum, and how invalid pixels are excluded.
- Camera calibration, environmental compensation, and measurement quality handling.
- The rules that assign `normal`, `low`, or `elevated`.

The current packet has one temperature value and a status. It does not describe the measurement region, statistic, quality, or uncertainty. These would require a contract extension if they need to be shown or enforced in the app. Do not interpret an unspecified apparent surface temperature as a measured core body temperature. Missing temperature data should remain unavailable rather than be fabricated.

## Capture timing and drone inputs

Use the **capture time**, not the time detection finishes or the packet reaches the laptop. Camera and drone timestamps need a shared clock, or a measured camera-to-telemetry clock offset in the location settings.

The current matcher accepts an exact telemetry timestamp or interpolates between two telemetry packets no more than 500 ms apart. It does not extrapolate. Frame or telemetry arrival gaps longer than 2 seconds withhold person locations. Frames are buffered by ID, so detections may arrive after their image, within the bounded buffer and timing checks.

The drone separately supplies:

- Valid, fresh latitude and longitude, with `fix_valid: true` and a connected link.
- `altitude_m` above sea level, as confirmed for this project. Subtract compatible ground elevation to obtain clearance; do not add terrain elevation to an already absolute altitude.
- Roll, pitch, and yaw at capture time, using the confirmed attitude conventions.
- A north-referenced heading, or the information needed to establish the offset from relative yaw. Relative yaw alone does not provide north. GPS course calibration is accepted only during confirmed steady forward flight with sufficient motion.

Location settings also supply the forward-facing camera mount angle, currently **20° down from horizontal**, image/attitude convention confirmation, clock offset, and ground elevation. The current optical model is provisional; measured camera intrinsics would improve it. Correct packets do not by themselves validate real-world location accuracy.

## Current browser integration

The ground-station location adapter listens for these browser events:

```ts
window.dispatchEvent(new CustomEvent("vigil:frame", { detail: framePacket }));
window.dispatchEvent(new CustomEvent("vigil:detection", { detail: detectionPacket }));
```

Drone telemetry is received separately through the telemetry adapter or `vigil:telemetry` event. These browser events are an internal interface; the Wi-Fi receiver must decode its network messages and forward validated packets to them. This document does not define a new network endpoint.

## Integration acceptance checks

1. A native image and its detection packet use the same frame ID and capture timestamp context.
2. The box overlay aligns with the person before coordinate projection is enabled.
3. A stationary tracked person retains its ID between frames; an empty detection array clears people for that capture.
4. Clipped boxes and explicitly obscured feet do not create location pins.
5. Stopping either feed withholds person coordinates after the stale-input deadline.
6. Temperature is unavailable when a radiometric measurement is missing; low and high indicators use the agreed measurement policy.
7. Surveyed ground points are used to measure real-world position error before relying on the estimates.

## Items the camera/detection team still needs to decide

- The Wi-Fi transport and receiver/decoder implementation.
- How the camera capture clock is synchronized with drone telemetry.
- How feet visibility and stable tracking IDs are determined.
- Which radiometric measurement is reported and how its status is assigned.
- Whether camera intrinsics and distortion calibration will replace the provisional projection model.
