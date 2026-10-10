"""Shared temporal-stack helpers for dataset preparation and live inference.

A temporal image packs grayscale frames [t - 2k, t - k, t] into the B, G, R channels of
one 3-channel image. OpenCV and Ultralytics both treat numpy arrays as BGR, so writing
the stack with cv2.imwrite and passing the same array to model.predict stay consistent.
"""

from __future__ import annotations

import cv2
import numpy as np


ALIGN_MODES = ("none", "phase")


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    raise ValueError(f"Unsupported image shape: {image.shape}")


def align_to(reference: np.ndarray, moving: np.ndarray, max_shift_fraction: float = 0.25) -> np.ndarray:
    """Translate `moving` onto `reference` with phase correlation (compensates drone drift)."""
    if reference.shape != moving.shape:
        raise ValueError("Frames must share a shape before alignment")
    window = cv2.createHanningWindow(reference.shape[::-1], cv2.CV_32F)
    (shift_x, shift_y), response = cv2.phaseCorrelate(
        moving.astype(np.float32), reference.astype(np.float32), window
    )
    height, width = reference.shape
    if response < 0.05 or abs(shift_x) > width * max_shift_fraction or abs(shift_y) > height * max_shift_fraction:
        return moving
    matrix = np.float32([[1, 0, shift_x], [0, 1, shift_y]])
    return cv2.warpAffine(moving, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)


def stack_frames(frames: list[np.ndarray], align: str = "none") -> np.ndarray:
    """Return an HxWx3 uint8 stack of [oldest, middle, current] grayscale frames."""
    if len(frames) != 3:
        raise ValueError("A temporal stack needs exactly three frames")
    if align not in ALIGN_MODES:
        raise ValueError(f"align must be one of {ALIGN_MODES}")
    grays = [to_gray(frame) for frame in frames]
    current = grays[-1]
    if any(gray.shape != current.shape for gray in grays):
        raise ValueError("All frames in a temporal stack must share a shape")
    if align == "phase":
        grays = [align_to(current, gray) for gray in grays[:-1]] + [current]
    return np.dstack(grays).astype(np.uint8)
