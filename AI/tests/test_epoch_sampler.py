from __future__ import annotations

import unittest

from AI.scripts.epoch_sampler import PresenceSourceSampler, allocate_balanced, presence_metrics


class EpochSamplerTests(unittest.TestCase):
    def test_presence_metrics(self) -> None:
        metrics = presence_metrics(tp=80, fp=20, fn=20, tn=80)
        self.assertAlmostEqual(metrics["metrics/presence_precision"], 0.8)
        self.assertAlmostEqual(metrics["metrics/presence_recall"], 0.8)
        self.assertAlmostEqual(metrics["metrics/presence_f1"], 0.8)
        self.assertAlmostEqual(metrics["metrics/presence_specificity"], 0.8)
        self.assertAlmostEqual(metrics["metrics/false_positive_frame_rate"], 0.2)

    def test_balanced_allocation_redistributes_small_group_capacity(self) -> None:
        groups = {"short": [0], "long_a": list(range(10)), "long_b": list(range(10))}
        allocation = allocate_balanced(groups, 9, __import__("random").Random(26))
        self.assertEqual(allocation["short"], 1)
        self.assertEqual(sum(allocation.values()), 9)
        self.assertLessEqual(abs(allocation["long_a"] - allocation["long_b"]), 1)

    def test_sampler_is_deterministic_within_epoch_and_refreshes_between_epochs(self) -> None:
        groups = ["long"] * 12 + ["short"] * 4
        positive = [True] * 8 + [False] * 4 + [True] * 2 + [False] * 2
        sampler = PresenceSourceSampler(groups, positive, 0.5, 26)
        epoch_zero = list(sampler)
        self.assertEqual(epoch_zero, list(sampler))
        sampler.set_epoch(1)
        epoch_one = list(sampler)
        self.assertNotEqual(epoch_zero, epoch_one)
        self.assertEqual(len(epoch_zero), 8)
        self.assertEqual(len(epoch_zero), len(set(epoch_zero)))

    def test_sampler_preserves_presence_ratio_and_balances_sources(self) -> None:
        groups = ["a"] * 100 + ["b"] * 20 + ["c"] * 20
        positive = [True] * 60 + [False] * 40 + [True] * 10 + [False] * 10 + [True] * 10 + [False] * 10
        sampler = PresenceSourceSampler(groups, positive, 0.5, 7)
        selected = list(sampler)
        self.assertEqual(sum(positive[index] for index in selected), sampler.positive_count)
        counts = {group: sum(groups[index] == group for index in selected) for group in set(groups)}
        self.assertLess(counts["a"], 50)  # long source no longer contributes proportionally
        self.assertGreaterEqual(counts["b"], 20)  # smaller sources are fully represented
        self.assertGreaterEqual(counts["c"], 20)

    def test_sampler_supports_explicit_hard_negative_mix(self) -> None:
        groups = [f"source_{index % 4}" for index in range(100)]
        positive = [True] * 50 + [False] * 50
        hard = [False] * 50 + [True] * 25 + [False] * 25
        sampler = PresenceSourceSampler(
            groups,
            positive,
            0.4,
            26,
            hard_negative=hard,
            positive_fraction=0.5,
            hard_negative_fraction=0.25,
        )
        selected = list(sampler)
        self.assertEqual(len(selected), 40)
        self.assertEqual(sum(positive[index] for index in selected), 20)
        self.assertEqual(sum(hard[index] for index in selected), 10)
        self.assertEqual(sum(not positive[index] and not hard[index] for index in selected), 10)

    def test_sampler_rejects_positive_hard_negative(self) -> None:
        with self.assertRaises(ValueError):
            PresenceSourceSampler(
                ["a", "a"], [True, False], 1.0, 1, hard_negative=[True, False]
            )


if __name__ == "__main__":
    unittest.main()
