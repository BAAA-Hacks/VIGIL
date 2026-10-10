from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from AI.scripts.build_folds import ImageRecord, SequenceStats, read_sequence_names, write_folds
from AI.scripts.inspect_dataset import duplicate_content_report, sequence_overlap
from AI.scripts.import_wisard_raw import clip_small_boundary_overflow, declared_human_count
from AI.scripts.dataset_utils import (
    YoloBox,
    label_path_for_image,
    load_dataset_config,
    source_frame_id,
    split_images,
)
from AI.scripts.select_holdout_sequences import choose_holdout
from AI.scripts.prepare_medium_crops import centered_crop_bounds, crop_boxes, medium_crop_bounds


class DatasetPreflightTests(unittest.TestCase):
    def test_centered_negative_crop_preserves_aspect_and_scale(self) -> None:
        bounds = centered_crop_bounds(640, 512, 0.5, 4 / 3)
        left, top, right, bottom = bounds
        self.assertAlmostEqual((right - left) / (bottom - top), 4 / 3, places=2)
        self.assertAlmostEqual((left + right) / 2, 320, delta=0.5)
        self.assertAlmostEqual((top + bottom) / 2, 256, delta=0.5)

    def test_medium_crop_enlarges_centered_person_and_preserves_aspect(self) -> None:
        box = YoloBox(0, 0.5, 0.5, 0.1, 0.2)
        bounds = medium_crop_bounds(640, 512, [box], 0.5, 4 / 3, 0.15)
        left, top, right, bottom = bounds
        self.assertAlmostEqual((right - left) / (bottom - top), 4 / 3, places=2)
        cropped = crop_boxes([box], 640, 512, bounds, 0.5)
        self.assertEqual(len(cropped), 1)
        self.assertGreater(cropped[0].width, box.width)
        self.assertGreater(cropped[0].height, box.height)

    def test_medium_crop_expands_to_keep_separated_people(self) -> None:
        boxes = [
            YoloBox(0, 0.1, 0.5, 0.1, 0.2),
            YoloBox(0, 0.9, 0.5, 0.1, 0.2),
        ]
        bounds = medium_crop_bounds(640, 480, boxes, 0.5, 4 / 3, 0.1)
        cropped = crop_boxes(boxes, 640, 480, bounds, 0.99)
        self.assertEqual(len(cropped), 2)

    def test_crop_boxes_drops_mostly_hidden_box(self) -> None:
        box = YoloBox(0, 0.75, 0.5, 0.5, 0.5)
        cropped = crop_boxes([box], 100, 100, (0, 0, 40, 100), 0.5)
        self.assertEqual(cropped, [])

    def test_source_frame_id_accepts_space_before_frame_number(self) -> None:
        sequence, frame = source_frame_id(Path("flight__FLIR_1_ 0097.jpg"))
        self.assertEqual(sequence, "flight__FLIR_1")
        self.assertEqual(frame, 97)

    def test_split_images_preserves_canonical_symlink_and_label_pairing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.jpg"
            raw.write_bytes(b"raw")
            images = root / "dataset" / "images"
            labels = root / "dataset" / "labels"
            images.mkdir(parents=True)
            labels.mkdir(parents=True)
            link = images / "flight_0001.jpg"
            link.symlink_to(raw)
            canonical_label = labels / "flight_0001.txt"
            canonical_label.write_text("", encoding="utf-8")
            data_yaml = root / "dataset" / "data.yaml"
            data_yaml.write_text(
                yaml.safe_dump(
                    {"path": str(root / "dataset"), "train": str(images), "names": {0: "person"}}
                ),
                encoding="utf-8",
            )

            found = split_images(load_dataset_config(data_yaml), "train")
            self.assertEqual(found, [link])
            self.assertEqual(label_path_for_image(found[0]), canonical_label)

    def test_small_box_boundary_overflow_is_clipped(self) -> None:
        clipped, changed = clip_small_boundary_overflow(
            YoloBox(0, 0.5, 0.001, 0.1, 0.004)
        )
        self.assertTrue(changed)
        self.assertEqual(clipped.y_center - clipped.height / 2, 0.0)

    def test_large_box_boundary_overflow_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            clip_small_boundary_overflow(YoloBox(0, 0.5, 0.0, 0.1, 0.1))

    def test_declared_human_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "count.txt").write_text("number of humans: 0\n", encoding="utf-8")
            self.assertEqual(declared_human_count(root), 0)

    def test_holdout_selection_is_deterministic_and_sequence_grouped(self) -> None:
        sequences = {
            f"flight_{index}": SequenceStats(
                name=f"flight_{index}",
                images=[
                    ImageRecord(Path(f"/flight_{index}_{frame}.png"), f"flight_{index}", 1, 1, [])
                    for frame in range(index + 1)
                ],
                annotations=(index + 1) * 2,
                tiny_annotations=index,
            )
            for index in range(12)
        }
        first, first_report = choose_holdout(sequences, 0.25, 26)
        second, second_report = choose_holdout(sequences, 0.25, 26)
        self.assertEqual(first, second)
        self.assertEqual(first_report, second_report)
        self.assertTrue(first)
        self.assertLess(len(first), len(sequences))

    def test_duplicate_report_separates_cross_split_duplicates(self) -> None:
        groups = {
            "same": [("train", Path("a.png")), ("val", Path("b.png"))],
            "within": [("train", Path("c.png")), ("train", Path("d.png"))],
            "unique": [("test", Path("e.png"))],
        }
        report = duplicate_content_report(groups)
        self.assertEqual(report["duplicate_groups"], 2)
        self.assertEqual(report["cross_split_duplicate_groups"], 1)
        self.assertEqual(report["cross_split_group_counts"], {"train_val": 1})

    def test_sequence_audit_flags_unparsed_and_overlapping_video(self) -> None:
        report = sequence_overlap(
            {
                "train": [
                    Path("flight_0001_jpg.rf.aaa.png"),
                    Path("flight_0002_jpg.rf.bbb.png"),
                ],
                "val": [
                    Path("flight_0003_jpg.rf.ccc.png"),
                    Path("unparsed_jpg.rf.ddd.png"),
                ],
            }
        )
        self.assertEqual(report["pairwise"]["train_val"]["shared_sequences"], ["flight"])
        self.assertEqual(report["parser_audit"]["val"]["frames_without_parsed_number"], 1)

    def test_holdout_sequence_file_accepts_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "holdout.txt"
            path.write_text("# locked before training\nflight_b\n\nflight_a\n", encoding="utf-8")
            self.assertEqual(read_sequence_names(path), {"flight_a", "flight_b"})

    def test_locked_sequence_is_only_written_to_test_split(self) -> None:
        def stats(name: str) -> SequenceStats:
            return SequenceStats(
                name=name,
                images=[ImageRecord(Path(f"/{name}.png"), name, 1, 1, [])],
            )

        sequences = {name: stats(name) for name in ("flight_a", "flight_b", "flight_test")}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_folds(
                SimpleNamespace(names={0: "person"}),
                sequences,
                {"flight_a": 0, "flight_b": 1},
                {},
                root,
                2,
                26,
                {"flight_test"},
            )
            for index in range(2):
                fold = root / f"fold_{index}"
                train = (fold / "train.txt").read_text(encoding="utf-8")
                validation = (fold / "val.txt").read_text(encoding="utf-8")
                test = (fold / "test.txt").read_text(encoding="utf-8")
                config = yaml.safe_load((fold / "data.yaml").read_text(encoding="utf-8"))
                self.assertNotIn("flight_test", train)
                self.assertNotIn("flight_test", validation)
                self.assertIn("flight_test", test)
                self.assertIn("test", config)


if __name__ == "__main__":
    unittest.main()
