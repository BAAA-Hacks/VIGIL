#!/usr/bin/env python3
"""Make Lepton-like degraded copies of a YOLO image folder (motion smear, noise, AGC).

The Lepton 3.5 is a slow microbolometer at ~9 fps, so movement leaves directional blur
and a lagging ghost, and its frames carry temporal and column/row fixed-pattern noise
under per-frame min-max gain. Clean stills never show these, and live confidence drops
sharply on moving people. Each output keeps the source label unchanged.

  src/{images,labels}  ->  out/train/{images,labels}   (ready for add_external_stills.py)
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import cv2
import numpy as np


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Folder with images/ and labels/")
    parser.add_argument("output", type=Path, help="Output root; writes <output>/<split>/{images,labels}")
    parser.add_argument("--split", default="train")
    parser.add_argument("--variants", type=int, default=1, help="Degraded copies per source image")
    parser.add_argument("--limit", type=int, default=0, help="Use at most N source images (0 = all)")
    parser.add_argument("--seed", type=int, default=26)
    return parser.parse_args()


def line_kernel(length: int, angle_deg: float) -> np.ndarray:
    kernel = np.zeros((length, length), np.float32)
    kernel[length // 2, :] = 1.0
    rotation = cv2.getRotationMatrix2D((length / 2 - 0.5, length / 2 - 0.5), angle_deg, 1.0)
    kernel = cv2.warpAffine(kernel, rotation, (length, length))
    return kernel / max(kernel.sum(), 1e-6)


def motion_smear(image: np.ndarray, rng: random.Random) -> np.ndarray:
    """Directional blur plus a lagging ghost, as a moving target leaves on a bolometer."""
    length = rng.choice((3, 5, 7, 9, 11, 13))
    angle = rng.uniform(0, 180)
    blurred = cv2.filter2D(image, -1, line_kernel(length, angle), borderType=cv2.BORDER_REFLECT)
    if rng.random() < 0.6:
        radians = np.deg2rad(angle)
        distance = rng.uniform(2, 8)
        shift = np.float32([[1, 0, distance * np.cos(radians)], [0, 1, distance * np.sin(radians)]])
        ghost = cv2.warpAffine(blurred, shift, image.shape[1::-1], borderMode=cv2.BORDER_REFLECT)
        keep = rng.uniform(0.55, 0.85)
        blurred = keep * blurred + (1 - keep) * ghost
    return blurred


def subject_mask(shape: tuple[int, int], boxes: list[list[float]], rng: random.Random) -> np.ndarray:
    """Soft mask over the labelled people, so only the subject moves (static camera)."""
    height, width = shape
    mask = np.zeros(shape, np.float32)
    for _, x, y, w, h in boxes:
        grow = rng.uniform(1.05, 1.3)
        left, right = int((x - w * grow / 2) * width), int((x + w * grow / 2) * width)
        top, bottom = int((y - h * grow / 2) * height), int((y + h * grow / 2) * height)
        mask[max(0, top):min(height, bottom), max(0, left):min(width, right)] = 1.0
    return cv2.GaussianBlur(mask, (0, 0), 3)


def sensor_noise(image: np.ndarray, rng: random.Random, np_rng: np.random.Generator) -> np.ndarray:
    height, width = image.shape
    noisy = image + np_rng.normal(0, rng.uniform(1.0, 4.0), image.shape)
    noisy += np_rng.normal(0, rng.uniform(0.0, 2.5), (1, width))   # column fixed-pattern noise
    noisy += np_rng.normal(0, rng.uniform(0.0, 1.5), (height, 1))  # row noise
    return noisy


def lepton_agc(image: np.ndarray) -> np.ndarray:
    """Per-frame min-max gain, matching lepton_live.normalize_frame."""
    low, high = float(image.min()), float(image.max())
    return (image - low) * 255.0 / max(high - low, 1.0)


def degrade(image: np.ndarray, boxes: list[list[float]], rng: random.Random, np_rng) -> np.ndarray:
    work = image.astype(np.float32)
    mode = rng.random()
    if mode < 0.45 and boxes:
        mask = subject_mask(work.shape, boxes, rng)
        work = mask * motion_smear(work, rng) + (1 - mask) * work
    elif mode < 0.8:
        work = motion_smear(work, rng)  # camera pan or shake: whole frame
    if rng.random() < 0.3:
        work = cv2.GaussianBlur(work, (0, 0), rng.uniform(0.5, 1.2))  # focus / optics softness
    work = sensor_noise(work, rng, np_rng)
    if rng.random() < 0.7:
        work = lepton_agc(work)
    return np.clip(work, 0, 255).astype(np.uint8)


def read_boxes(label: Path) -> list[list[float]]:
    if not label.is_file():
        return []
    return [list(map(float, line.split()[:5])) for line in label.read_text().splitlines() if line.strip()]


def main() -> None:
    args = parse_args()
    if args.variants <= 0 or args.limit < 0:
        raise SystemExit("--variants must be positive and --limit cannot be negative")
    rng = random.Random(args.seed)
    np_rng = np.random.default_rng(args.seed)
    source = args.source.expanduser().resolve()
    images = sorted(p for p in (source / "images").iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if args.limit:
        images = rng.sample(images, min(args.limit, len(images)))
    out_images = args.output.expanduser().resolve() / args.split / "images"
    out_labels = out_images.parent / "labels"
    out_images.mkdir(parents=True, exist_ok=True)
    out_labels.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in images:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise SystemExit(f"Could not decode {path}")
        label = source / "labels" / f"{path.stem}.txt"
        boxes = read_boxes(label)
        for variant in range(args.variants):
            stem = f"{path.stem}_aug{variant}"
            cv2.imwrite(str(out_images / f"{stem}.png"), degrade(image, boxes, rng, np_rng))
            (out_labels / f"{stem}.txt").write_text(label.read_text() if label.is_file() else "")
            written += 1
    print(f"Wrote {written} degraded images to {out_images}")


if __name__ == "__main__":
    main()
