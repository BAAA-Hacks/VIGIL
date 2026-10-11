from __future__ import annotations

import io
import struct
import unittest

import numpy as np

from AI.scripts.lepton_live import (
    HEADER,
    IdentityStitcher,
    LeptonFrame,
    center_temperature_c,
    feet_visible,
    flip_frame,
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

    def test_flip_180_puts_the_top_left_pixel_bottom_right(self) -> None:
        pixels = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint16)
        frame = LeptonFrame(1, 1, 3, 2, 1, 6, 1, pixels)
        np.testing.assert_array_equal(flip_frame(frame, "180").pixels, [[6, 5, 4], [3, 2, 1]])
        np.testing.assert_array_equal(flip_frame(frame, "horizontal").pixels, [[3, 2, 1], [6, 5, 4]])
        self.assertIs(flip_frame(frame, "none"), frame)

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



class IdentityStitcherTests(unittest.TestCase):
    @staticmethod
    def person(track: int, x: float, height: float = 0.3, held: bool = False) -> dict:
        return {"tracking_id": track, "bbox": [x, 0.3, x + 0.1, 0.3 + height], "confidence": 0.8, "held": held}

    def test_a_person_who_reappears_nearby_keeps_their_id(self) -> None:
        stitcher = IdentityStitcher(8.0)
        self.assertEqual(stitcher.apply([self.person(1, 0.40)], 0.0)[0]["tracking_id"], 1)
        self.assertEqual(stitcher.apply([self.person(5, 0.45)], 1.0)[0]["tracking_id"], 1)
        self.assertEqual(stitcher.apply([self.person(5, 0.47)], 1.1)[0]["tracking_id"], 1)

    def test_lone_person_keeps_their_id_after_the_camera_turns(self) -> None:
        stitcher = IdentityStitcher(8.0)
        stitcher.apply([self.person(1, 0.80)], 0.0)
        self.assertEqual(stitcher.apply([self.person(5, 0.05)], 3.0)[0]["tracking_id"], 1)

    def test_far_reappearance_with_others_in_view_is_a_new_person(self) -> None:
        stitcher = IdentityStitcher(8.0)
        stitcher.apply([self.person(1, 0.80), self.person(2, 0.10)], 0.0)
        ids = {p["tracking_id"] for p in stitcher.apply([self.person(2, 0.10), self.person(7, 0.05, 0.31)], 0.5)}
        self.assertEqual(ids, {2, 7})

    def test_ids_are_forgotten_after_the_memory_window(self) -> None:
        stitcher = IdentityStitcher(8.0)
        stitcher.apply([self.person(1, 0.40)], 0.0)
        self.assertEqual(stitcher.apply([self.person(5, 0.40)], 9.0)[0]["tracking_id"], 5)

    def test_held_box_is_dropped_when_its_person_has_a_live_box(self) -> None:
        stitcher = IdentityStitcher(8.0)
        stitcher.apply([self.person(1, 0.40)], 0.0)
        out = stitcher.apply([self.person(5, 0.42), self.person(1, 0.40, held=True)], 0.1)
        self.assertEqual([(p["tracking_id"], p["held"]) for p in out], [(1, False)])

if __name__ == "__main__":
    unittest.main()
