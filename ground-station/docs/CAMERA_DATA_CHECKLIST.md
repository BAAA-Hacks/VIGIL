For each thermal frame, send:

- **Thermal image:** native 160 × 120, without cropping, rotation, or mirroring.
- **Frame ID:** unique per capture.
- **Capture timestamp:** arrival time on the ground computer (no clock sync with telemetry).

For each detected person, send:

- **Bounding box:** `[left, top, right, bottom]`, normalized from 0 to 1. We calculate location from its bottom-center.
- **Person tracking ID:** stays consistent across frames.
- **Detection confidence:** from 0 to 1.
- **Feet visible:** true or false.
- **Center temperature:** temperature in °C at the center of the person’s bounding box.
- **Class:** `"person"`.

Also send **detection processing time in milliseconds**, and an **empty person list when nobody is detected**.

GPS, altitude, attitude, heading, and camera mount angle come from the drone/configuration separately.
