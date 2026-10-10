from __future__ import annotations

import io
import struct
import unittest

import numpy as np

from AI.scripts.lepton_live import (
    HEADER,
    LeptonFrame,
    center_temperature_c,
    feet_visible,
    hottest_temperature_c,
    normalize_frame,
    read_frame,
)


class LeptonLiveTests(unittest.TestCase):
    def test_binary_record_is_parsed_without_spatial_transform(self) -> None:
        pixels = np.arange(160 * 120, dtype=np.uint16).reshape(120, 160)
        header = HEADER.pack(b"LEP1", 42, 1234, 160, 120, 0, 19199, 1)
        frame = read_frame(io.BytesIO(header + pixels.astype("<u2").tobytes()))
        self.assertEqual(frame.camera_frame_id, 42)
        self.assertEqual(frame.pixels.shape, (120, 160))
        np.testing.assert_array_equal(frame.pixels, pixels)

    def test_normalization_uses_frame_minimum_and_maximum(self) -> None:
        pixels = np.array([[100, 150, 200]], dtype=np.uint16)
        frame = LeptonFrame(1, 1, 3, 1, 100, 200, 0, pixels)
        np.testing.assert_array_equal(normalize_frame(frame), np.array([[0, 127, 255]], dtype=np.uint8))

    def test_temperature_requires_tlinear_and_samples_box_center(self) -> None:
        pixels = np.full((120, 160), 30000, dtype=np.uint16)
        tlinear = LeptonFrame(1, 1, 160, 120, 0, 65535, 1, pixels)
        relative = LeptonFrame(1, 1, 160, 120, 0, 65535, 0, pixels)
        self.assertEqual(center_temperature_c(tlinear, [0.4, 0.4, 0.6, 0.6]), 26.85)
        self.assertIsNone(center_temperature_c(relative, [0.4, 0.4, 0.6, 0.6]))

    def test_hottest_temperature_flags_hot_objects_inside_box(self) -> None:
        pixels = np.full((120, 160), int((30 + 273.15) * 100), dtype=np.uint16)
        pixels[50:60, 70:80] = int((70 + 273.15) * 100)
        tlinear = LeptonFrame(1, 1, 160, 120, 0, 65535, 1, pixels)
        self.assertGreater(hottest_temperature_c(tlinear, [0.4, 0.38, 0.52, 0.52]), 60)
        self.assertLess(hottest_temperature_c(tlinear, [0.0, 0.0, 0.2, 0.2]), 31)
        self.assertIsNone(hottest_temperature_c(LeptonFrame(1, 1, 160, 120, 0, 65535, 0, pixels), [0, 0, 1, 1]))

    def test_feet_visibility_is_conservative_at_image_edges(self) -> None:
        self.assertTrue(feet_visible([0.2, 0.2, 0.8, 0.9], 0.01))
        self.assertFalse(feet_visible([0.2, 0.2, 0.8, 1.0], 0.01))


if __name__ == "__main__":
    unittest.main()
