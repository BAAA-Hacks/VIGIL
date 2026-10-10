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


def presence_metrics(tp: int, fp: int, fn: int, tn: int) -> dict[str, float]:
    """Calculate frame-presence metrics used for checkpoint selection."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "metrics/presence_precision": precision,
        "metrics/presence_recall": recall,
        "metrics/presence_f1": f1,
        "metrics/presence_specificity": specificity,
        "metrics/false_positive_frame_rate": 1.0 - specificity,
    }


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
        hard_negative: Sequence[bool] | None = None,
        positive_fraction: float | None = None,
        hard_negative_fraction: float | None = None,
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
        self.hard_negative = list(hard_negative) if hard_negative is not None else [False] * len(positive)
        if len(self.hard_negative) != len(self.positive):
            raise ValueError("hard_negative must have the same length as positive")
        if any(hard and is_positive for hard, is_positive in zip(self.hard_negative, self.positive, strict=True)):
            raise ValueError("A positive image cannot also be a hard negative")
        self.uses_hard_negative_mix = positive_fraction is not None or hard_negative_fraction is not None
        if self.uses_hard_negative_mix:
            if positive_fraction is None or hard_negative_fraction is None:
                raise ValueError("positive_fraction and hard_negative_fraction must be provided together")
            if not 0 <= positive_fraction <= 1 or not 0 <= hard_negative_fraction <= 1:
                raise ValueError("category fractions must be between zero and one")
            if positive_fraction + hard_negative_fraction > 1:
                raise ValueError("positive and hard-negative fractions cannot sum above one")
            desired = {
                "positive": round(self.sample_count * positive_fraction),
                "hard_negative": round(self.sample_count * hard_negative_fraction),
            }
            desired["ordinary_negative"] = self.sample_count - sum(desired.values())
            capacities = {
                "positive": sum(self.positive),
                "hard_negative": sum(self.hard_negative),
                "ordinary_negative": sum(
                    not is_positive and not hard
                    for is_positive, hard in zip(self.positive, self.hard_negative, strict=True)
                ),
            }
            counts = {name: min(desired[name], capacities[name]) for name in desired}
            remaining = self.sample_count - sum(counts.values())
            for name in ("ordinary_negative", "positive", "hard_negative"):
                added = min(remaining, capacities[name] - counts[name])
                counts[name] += added
                remaining -= added
            if remaining:
                raise ValueError("Requested sample count exceeds category capacity")
            self.positive_count = counts["positive"]
            self.hard_negative_count = counts["hard_negative"]
            self.ordinary_negative_count = counts["ordinary_negative"]
            self.negative_count = self.hard_negative_count + self.ordinary_negative_count
        else:
            self.positive_count = round(self.sample_count * sum(self.positive) / len(self.positive))
            self.negative_count = self.sample_count - self.positive_count
            self.hard_negative_count = 0
            self.ordinary_negative_count = self.negative_count

    def __len__(self) -> int:
        return self.sample_count

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def __iter__(self) -> Iterator[int]:
        rng = random.Random(self.seed + self.epoch * 1_000_003)
        categories: dict[str, dict[str, list[int]]] = {
            "positive": defaultdict(list),
            "hard_negative": defaultdict(list),
            "ordinary_negative": defaultdict(list),
        }
        for index, (group, is_positive, hard) in enumerate(
            zip(self.source_groups, self.positive, self.hard_negative, strict=True)
        ):
            category = "positive" if is_positive else "hard_negative" if hard else "ordinary_negative"
            categories[category][group].append(index)

        selected: list[int] = []
        for category, quota in (
            ("positive", self.positive_count),
            ("hard_negative", self.hard_negative_count),
            ("ordinary_negative", self.ordinary_negative_count),
        ):
            groups = dict(categories[category])
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


def make_resampled_detection_trainer(
    fraction: float,
    seed: int,
    hard_negative_paths: set[Path] | None = None,
    positive_fraction: float | None = None,
    hard_negative_fraction: float | None = None,
    selection_metric: str = "map",
    presence_confidence: float = 0.4,
):
    """Create an Ultralytics trainer class configured for epoch resampling."""
    from ultralytics.data import build_dataloader
    from ultralytics.data.build import InfiniteDataLoader, seed_worker
    from ultralytics.models.yolo.detect import DetectionTrainer
    from ultralytics.models.yolo.detect.val import DetectionValidator
    from ultralytics.utils import LOGGER

    class PresenceDetectionValidator(DetectionValidator):
        def init_metrics(self, model) -> None:
            super().init_metrics(model)
            person_ids = [
                int(class_id)
                for class_id, name in self.names.items()
                if str(name).strip().casefold() == "person"
            ]
            if len(person_ids) != 1:
                raise RuntimeError(f"Expected one person class, found {person_ids}")
            self.person_class_id = person_ids[0]
            self.presence_counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}

        def update_metrics(self, preds, batch) -> None:
            super().update_metrics(preds, batch)
            for index, prediction in enumerate(preds):
                prepared = self._prepare_batch(index, batch)
                actual = bool((prepared["cls"] == self.person_class_id).any().item())
                predicted = bool(
                    (
                        (prediction["cls"] == self.person_class_id)
                        & (prediction["conf"] >= presence_confidence)
                    ).any().item()
                )
                key = "tp" if actual and predicted else "fn" if actual else "fp" if predicted else "tn"
                self.presence_counts[key] += 1

        def get_stats(self):
            stats = super().get_stats()
            metrics = presence_metrics(**self.presence_counts)
            stats.update(metrics)
            if selection_metric == "presence_f1":
                stats["fitness"] = metrics["metrics/presence_f1"]
            return stats

    class ResampledDetectionTrainer(DetectionTrainer):
        epoch_fraction = fraction
        sampler_seed = seed

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.add_callback("on_train_epoch_start", self._set_sampler_epoch)

        def get_validator(self):
            from copy import copy

            return PresenceDetectionValidator(
                self.test_loader,
                save_dir=self.save_dir,
                args=copy(self.args),
                _callbacks=self.callbacks,
            )

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
            normalized_paths = [Path(path).expanduser().resolve() for path in dataset.im_files]
            hard_flags = [path in hard_negative_paths for path in normalized_paths] if hard_negative_paths else None
            sampler = PresenceSourceSampler(
                dataset_source_groups(dataset),
                dataset_presence(dataset),
                self.epoch_fraction,
                self.sampler_seed,
                hard_negative=hard_flags,
                positive_fraction=positive_fraction,
                hard_negative_fraction=hard_negative_fraction,
            )
            batch_size = min(batch_size, len(sampler))
            batches = math.ceil(len(sampler) / batch_size)
            workers = min(os.cpu_count() or 1, self.args.workers, 0 if batches <= 1 else batches)
            generator = torch.Generator().manual_seed(6148914691236517205 + self.sampler_seed)
            LOGGER.info(
                "Epoch sampler: %d/%d images (%.1f%%), %d positive + %d hard negative + "
                "%d ordinary negative, balanced across source groups",
                len(sampler),
                len(dataset),
                100 * self.epoch_fraction,
                sampler.positive_count,
                sampler.hard_negative_count,
                sampler.ordinary_negative_count,
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

