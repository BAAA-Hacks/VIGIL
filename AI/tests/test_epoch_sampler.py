from __future__ import annotations

import unittest

from AI.scripts.epoch_sampler import PresenceSourceSampler, allocate_balanced


class EpochSamplerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
