# Live Lepton detection adapter

`AI.scripts.lepton_live` reads fixed-size records from the camera's `GET /raw` stream, preserves
the native unrotated/unmirrored 160 x 120 image, and publishes paired Socket.IO events.

Install dependencies and connect the computer to the `Lepton-Camera` Wi-Fi network:

```bash
python -m pip install -r requirements.txt

python -m AI.scripts.lepton_live \
  --weights AI/checkpoints/thermal_mega_medium_crop_fold0_best.pt \
  --camera-url http://192.168.4.1 \
  --socket-url http://GROUND-STATION:PORT \
  --device 0 \
  --conf 0.40
```

Omit `--socket-url` to print JSON-line events for testing. Add `--max-frames 10` for a bounded
camera smoke test.

## Events

`vigil:frame`:

```json
{
  "frame_id": "lepton-<process>-<camera-boot>-<camera-frame>",
  "capture_timestamp_ms": 1791648000000,
  "camera_timestamp_ms": 12345,
  "width": 160,
  "height": 120,
  "image_data_url": "data:image/png;base64,..."
}
```

`vigil:detection`:

```json
{
  "frame_id": "lepton-<process>-<camera-boot>-<camera-frame>",
  "capture_timestamp_ms": 1791648000000,
  "camera_timestamp_ms": 12345,
  "processing_ms": 7.25,
  "persons": [
    {
      "bbox": [0.1, 0.2, 0.3, 0.8],
      "bottom_center": [0.2, 0.8],
      "tracking_id": 1,
      "confidence": 0.91,
      "feet_visible": true,
      "center_temperature_c": 29.4,
      "class": "person"
    }
  ]
}
```

`persons` is an empty list when nobody is detected. `center_temperature_c` is `null` when the
camera record does not set the TLinear flag. The value is nominal TLinear conversion and is not a
calibrated body-temperature measurement. `feet_visible` is currently a conservative bounding-box
edge heuristic, not a pose-estimation result.

`capture_timestamp_ms` uses the ground computer's Unix clock. Keep that computer synchronized with
the telemetry clock (for example through the same NTP/GPS time source).
