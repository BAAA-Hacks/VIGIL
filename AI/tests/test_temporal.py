from __future__ import annotations

import unittest
from pathlib import Path

import cv2
import numpy as np

from AI.scripts.prepare_temporal import neighbour
from AI.scripts.temporal_utils import align_to, stack_frames


def blob_frame(x: int, y: int) -> np.ndarray:
    frame = np.full((120, 160), 40, dtype=np.uint8)
    cv2.circle(frame, (x, y), 6, 220, -1)
    cv2.rectangle(frame, (20, 90), (50, 110), 150, -1)
    return cv2.GaussianBlur(frame, (5, 5), 0)


class TemporalStackTests(unittest.TestCase):
    def test_channels_are_oldest_to_current(self) -> None:
        frames = [np.full((120, 160), value, dtype=np.uint8) for value in (10, 20, 30)]
        stacked = stack_frames(frames)
        self.assertEqual(stacked.shape, (120, 160, 3))
        self.assertEqual(stacked[0, 0].tolist(), [10, 20, 30])

    def test_phase_alignment_moves_neighbour_onto_reference(self) -> None:
        reference = blob_frame(80, 60)
        moved = np.roll(reference, shift=(4, -6), axis=(0, 1))
        aligned = align_to(reference, moved)
        error_before = np.abs(moved.astype(int) - reference).mean()
        error_after = np.abs(aligned.astype(int) - reference)[10:-10, 10:-10].mean()
        self.assertLess(error_after, error_before / 4)

    def test_mismatched_shapes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            stack_frames([np.zeros((120, 160), np.uint8), np.zeros((60, 80), np.uint8), np.zeros((120, 160), np.uint8)])


class NeighbourTests(unittest.TestCase):
    def test_exact_and_fallback_neighbours(self) -> None:
        frames = {index: Path(f"f{index}") for index in (1, 2, 4, 5)}
        self.assertEqual(neighbour(frames, 5, 1, 2), Path("f4"))
        self.assertEqual(neighbour(frames, 4, 1, 2), Path("f2"))
        self.assertIsNone(neighbour(frames, 1, 1, 2))
        self.assertIsNone(neighbour(frames, 5, 2, 2))


if __name__ == "__main__":
    unittest.main()
