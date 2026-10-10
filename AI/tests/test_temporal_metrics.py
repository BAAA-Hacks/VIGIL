from __future__ import annotations

import unittest
from pathlib import Path

from AI.scripts.temporal_metrics import (
    Detection,
    EvaluationFrame,
    box_iou,
    frame_metrics,
    sequence_metrics,
)
from AI.scripts.summarize_cv import choose_operating_points, pool_confidence_curves
from AI.scripts.balance_training_sequences import choose_negatives, evenly_spaced


GROUND_TRUTH = (0.1, 0.1, 0.3, 0.4)
MATCH = Detection(0.9, (0.12, 0.12, 0.28, 0.38))
FALSE_ALARM = Detection(0.8, (0.7, 0.7, 0.9, 0.9))


def make_frame(
    number: int,
    *,
    positive: bool,
    detections: tuple[Detection, ...] = (),
    derived_negative: bool = False,
) -> EvaluationFrame:
    return EvaluationFrame(
        image=Path(f"video_001-{number:04d}.png"),
        sequence="video_001",
        frame_number=number,
        derived_negative=derived_negative,
        ground_truth=(GROUND_TRUTH,) if positive else (),
        detections=detections,
    )


class FrameMetricTests(unittest.TestCase):
    def test_iou_identity(self) -> None:
        self.assertEqual(box_iou(GROUND_TRUTH, GROUND_TRUTH), 1.0)

    def test_presence_and_relaxed_matching(self) -> None:
        frames = [
            make_frame(1, positive=True, detections=(MATCH,)),
            make_frame(2, positive=True),
            make_frame(3, positive=False, detections=(FALSE_ALARM,)),
            make_frame(4, positive=False, derived_negative=True),
        ]
        metrics = frame_metrics(frames, 0.25, 0.25, "iou_or_center")
        self.assertEqual(metrics["tp_frames"], 1)
        self.assertEqual(metrics["fp_frames"], 1)
        self.assertEqual(metrics["fn_frames"], 1)
        self.assertEqual(metrics["tn_frames"], 1)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["matched_instances"], 1)
        self.assertEqual(metrics["relaxed_detection_precision"], 0.5)
        self.assertEqual(metrics["relaxed_detection_recall"], 0.5)
        self.assertEqual(metrics["derived_negative_frames"], 1)


class TemporalMetricTests(unittest.TestCase):
    def test_events_streaks_smoothing_and_negative_exclusion(self) -> None:
        frames = [
            make_frame(1, positive=True, detections=(MATCH,)),
            make_frame(2, positive=True),
            make_frame(3, positive=True, detections=(MATCH,)),
            make_frame(4, positive=False, detections=(FALSE_ALARM,)),
            make_frame(5, positive=True),
            make_frame(5, positive=False, detections=(FALSE_ALARM,), derived_negative=True),
        ]
        metrics = sequence_metrics(frames, 0.25, 0.25, "iou_or_center", 3, 2)
        self.assertEqual(metrics["timeline_frames"], 5)
        self.assertTrue(metrics["temporal_smoothing_eligible"])
        self.assertEqual(metrics["synthetic_negative_crops_excluded"], 1)
        self.assertEqual(metrics["raw"]["coverage"], 0.5)
        self.assertEqual(metrics["raw"]["longest_miss_streak_frames"], 1)
        self.assertEqual(metrics["raw"]["events"], 2)
        self.assertEqual(metrics["raw"]["detected_events"], 1)
        self.assertEqual(metrics["raw"]["event_recall"], 0.5)
        self.assertEqual(metrics["raw"]["false_alert_episodes"], 1)
        self.assertEqual(metrics["smoothed"]["coverage"], 0.5)
        self.assertEqual(metrics["smoothed"]["longest_miss_streak_frames"], 2)
        self.assertEqual(metrics["smoothed"]["event_recall"], 1.0)
        self.assertEqual(metrics["smoothed"]["false_alert_episodes"], 1)

    def test_short_sequence_is_marked_ineligible_for_k_of_n_summary(self) -> None:
        metrics = sequence_metrics(
            [make_frame(1, positive=True, detections=(MATCH,))],
            0.25,
            0.25,
            "iou_or_center",
            3,
            2,
        )
        self.assertFalse(metrics["temporal_smoothing_eligible"])
        self.assertEqual(metrics["smoothed"]["coverage"], 0.0)


class CrossValidationPoolingTests(unittest.TestCase):
    def test_confusion_counts_are_pooled_before_threshold_selection(self) -> None:
        reports = []
        for tp, fp, fn, matched, predicted in ((8, 2, 2, 7, 10), (4, 1, 6, 4, 6)):
            reports.append(
                (
                    Path("fold.json"),
                    {
                        "confidence_curve": [
                            {
                                "confidence_threshold": 0.25,
                                "tp_frames": tp,
                                "fp_frames": fp,
                                "fn_frames": fn,
                                "tn_frames": 10,
                                "ground_truth_instances": 10,
                                "predicted_instances": predicted,
                                "matched_instances": matched,
                            }
                        ]
                    },
                )
            )
        curve = pool_confidence_curves(reports)
        self.assertEqual(len(curve), 1)
        self.assertEqual(curve[0]["precision"], 0.8)
        self.assertEqual(curve[0]["recall"], 0.6)
        self.assertEqual(curve[0]["relaxed_detection_precision"], 0.6875)
        self.assertEqual(choose_operating_points(curve)["maximum_frame_f1"], curve[0])


class SequenceBalancingTests(unittest.TestCase):
    def test_evenly_spaced_selection_keeps_temporal_extent(self) -> None:
        images = [Path(f"flight_{frame:04d}.png") for frame in range(10)]
        selected = evenly_spaced(images, 4)
        self.assertEqual([path.stem for path in selected], [
            "flight_0000",
            "flight_0003",
            "flight_0006",
            "flight_0009",
        ])

    def test_short_sequence_is_not_oversampled(self) -> None:
        images = [Path("flight_0001.png"), Path("flight_0002.png")]
        self.assertEqual(evenly_spaced(images, 4), images)

    def test_all_negative_policy_does_not_discard_unselected_parent_negatives(self) -> None:
        negatives = {
            ("flight", 1): [Path("flight_0001_negative.png")],
            ("flight", 2): [Path("flight_0002_negative.png")],
        }
        selected_keys = {("flight", 1)}
        self.assertEqual(len(choose_negatives(negatives, selected_keys, "linked")), 1)
        self.assertEqual(len(choose_negatives(negatives, selected_keys, "all")), 2)


if __name__ == "__main__":
    unittest.main()
