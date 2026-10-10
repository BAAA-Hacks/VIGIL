"""Deterministic epoch-resampled training for video-correlated detection datasets."""

from __future__ import annotations

import math
import os
import random
from collections import defaultdict
from pathlib import Path
from typing import Iterator, Sequence

import torch
from torch.utils.data import Sampler

from AI.scripts.dataset_utils import source_frame_id


def allocate_balanced(
    groups: dict[str, list[int]], quota: int, rng: random.Random
) -> dict[str, int]:
    """Allocate a quota as evenly as capacities allow, with seeded tie-breaking."""
    if quota < 0 or quota > sum(map(len, groups.values())):
        raise ValueError("quota must be between zero and the available item count")
    allocated = dict.fromkeys(groups, 0)
    active = sorted(key for key, values in groups.items() if values)
    remaining = quota
    while remaining and active:
        order = list(active)
        rng.shuffle(order)
        for key in order:
            if not remaining:
                break
            if allocated[key] < len(groups[key]):
                allocated[key] += 1
                remaining -= 1
        active = [key for key in active if allocated[key] < len(groups[key])]
    if remaining:
        raise RuntimeError(f"Could not allocate {remaining} requested samples")
    return allocated


class PresenceSourceSampler(Sampler[int]):
    """Resample each epoch while preserving presence ratio and balancing sources."""

    def __init__(
        self,
        source_groups: Sequence[str],
        positive: Sequence[bool],
        fraction: float,
        seed: int,
    ) -> None:
        if len(source_groups) != len(positive) or not source_groups:
            raise ValueError("source_groups and positive must be non-empty and equally sized")
        if not 0.0 < fraction <= 1.0:
            raise ValueError("fraction must be in (0, 1]")
        self.source_groups = list(source_groups)
        self.positive = list(positive)
        self.fraction = fraction
        self.seed = seed
        self.epoch = 0
        self.sample_count = max(1, round(len(self.positive) * fraction))
        self.positive_count = round(self.sample_count * sum(self.positive) / len(self.positive))
        self.negative_count = self.sample_count - self.positive_count

    def __len__(self) -> int:
        return self.sample_count

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def __iter__(self) -> Iterator[int]:
        rng = random.Random(self.seed + self.epoch * 1_000_003)
        by_presence: dict[bool, dict[str, list[int]]] = {
            True: defaultdict(list),
            False: defaultdict(list),
        }
        for index, (group, is_positive) in enumerate(zip(self.source_groups, self.positive, strict=True)):
            by_presence[is_positive][group].append(index)

        selected: list[int] = []
        for is_positive, quota in ((True, self.positive_count), (False, self.negative_count)):
            groups = dict(by_presence[is_positive])
            capacity = sum(map(len, groups.values()))
            quota = min(quota, capacity)
            allocation = allocate_balanced(groups, quota, rng)
            for group in sorted(groups):
                count = allocation[group]
                if count:
                    selected.extend(rng.sample(groups[group], count))

        # One polarity can be absent in small/custom datasets. Fill any shortfall
        # from all remaining indices without replacement.
        if len(selected) < self.sample_count:
            selected_set = set(selected)
            remaining = [index for index in range(len(self.positive)) if index not in selected_set]
            selected.extend(rng.sample(remaining, self.sample_count - len(selected)))
        rng.shuffle(selected)
        return iter(selected)


def dataset_source_groups(dataset) -> list[str]:
    """Infer stable source groups from canonical image filenames."""
    return [source_frame_id(Path(path))[0] for path in dataset.im_files]


def dataset_presence(dataset) -> list[bool]:
    """Return whether each Ultralytics dataset item contains at least one box."""
    if len(dataset.labels) != len(dataset.im_files):
        raise RuntimeError("Ultralytics image/label inventories are misaligned")
    return [bool(len(label.get("cls", ()))) for label in dataset.labels]


def make_resampled_detection_trainer(fraction: float, seed: int):
    """Create an Ultralytics trainer class configured for epoch resampling."""
    from ultralytics.data import build_dataloader
    from ultralytics.data.build import InfiniteDataLoader, seed_worker
    from ultralytics.models.yolo.detect import DetectionTrainer
    from ultralytics.utils import LOGGER

    class ResampledDetectionTrainer(DetectionTrainer):
        epoch_fraction = fraction
        sampler_seed = seed

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.add_callback("on_train_epoch_start", self._set_sampler_epoch)

        @staticmethod
        def _set_sampler_epoch(trainer) -> None:
            sampler = getattr(trainer.train_loader, "sampler", None)
            if isinstance(sampler, PresenceSourceSampler):
                sampler.set_epoch(trainer.epoch)

        def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train"):
            if mode != "train":
                return build_dataloader(
                    self.build_dataset(dataset_path, mode, batch_size),
                    batch=batch_size,
                    workers=self.args.workers * 2,
                    shuffle=False,
                    rank=rank,
                    device=self.device,
                )
            if rank != -1:
                raise RuntimeError("Epoch-resampled training currently supports one GPU only")

            dataset = self.build_dataset(dataset_path, mode, batch_size)
            sampler = PresenceSourceSampler(
                dataset_source_groups(dataset),
                dataset_presence(dataset),
                self.epoch_fraction,
                self.sampler_seed,
            )
            batch_size = min(batch_size, len(sampler))
            batches = math.ceil(len(sampler) / batch_size)
            workers = min(os.cpu_count() or 1, self.args.workers, 0 if batches <= 1 else batches)
            generator = torch.Generator().manual_seed(6148914691236517205 + self.sampler_seed)
            LOGGER.info(
                "Epoch sampler: %d/%d images (%.1f%%), %d positive + %d negative, "
                "balanced across source groups",
                len(sampler),
                len(dataset),
                100 * self.epoch_fraction,
                sampler.positive_count,
                sampler.negative_count,
            )
            return InfiniteDataLoader(
                dataset=dataset,
                batch_size=batch_size,
                shuffle=False,
                sampler=sampler,
                num_workers=workers,
                prefetch_factor=4 if workers else None,
                pin_memory=getattr(self.device, "type", str(self.device)) not in {"cpu", "mps"},
                collate_fn=getattr(dataset, "collate_fn", None),
                worker_init_fn=seed_worker,
                generator=generator,
                drop_last=self.args.compile and len(sampler) > batch_size,
            )

    ResampledDetectionTrainer.__name__ = "ResampledDetectionTrainer"
    return ResampledDetectionTrainer

