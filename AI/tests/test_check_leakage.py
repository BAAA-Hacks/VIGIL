from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from AI.scripts.benchmark import mean_std, summarize
from AI.scripts.check_leakage import find_leaks, image_sequence_key, sequence_key
from AI.scripts.portable_paths import portable_dataset_yaml, rebase_repo_path


class SequenceKeyTests(unittest.TestCase):
    def test_wisard_full_names_match_old_roboflow_names(self) -> None:
        pairs = [
            ("200704_Baker_FLIR_IR_2__200704_baker_FLIR_2", "200704_baker_FLIR_2_"),
            ("200704_Baker_FLIR_IR_1__200704_baker__FLIR_1", "200704_baker__FLIR_1_"),
            (
                "210327_Airfield_FLIR_IR_6__20210327_115741_IR_H264 (1-6-2022 8-27-56 AM).mp4",
                "20210327_115741_IR_H264-1-6-2022-8-27-56-AM-mp4",
            ),
            ("220109_Baker_Enterprise_IR_1__DJI_0583 (1-10-2022 2-51-48 PM).mp4", "DJI_0583-1-10-2022-2-51-48-PM-mp4"),
            (
                "210417_MtErie_Enterprise_IR_0008__210417_MtErie_Enterprise_IR_0008_out_frame",
                "210417_MtErie_Enterprise_IR_0008_out_frame",
            ),
            ("210327_Airfield_FLIR_IR_8__210327_Airfield_FLIR_8_IR_8", "210327_Airfield_FLIR_8_IR_8"),
            ("210924_FHL_Enterprise_IR_0408__DJI_0408.mp4", "DJI_0408"),
        ]
        for new, old in pairs:
            with self.subTest(new=new):
                self.assertEqual(sequence_key(new), sequence_key(old))

    def test_distinct_sequences_stay_distinct(self) -> None:
        names = [
            "200704_Baker_FLIR_IR_1__200704_baker__FLIR_1",
            "200704_Baker_FLIR_IR_2__200704_baker_FLIR_2",
            "220109_Baker_Enterprise_IR_1__DJI_0583 (1-10-2022 2-51-48 PM).mp4",
            "220109_Baker_Enterprise_IR_2__DJI_0585 (1-10-2022 2-52-01 PM).mp4",
            "210417_MtErie_Enterprise_IR_0006__210417_MtErie_Enterprise_IR_0006",
            "210417_MtErie_Enterprise_IR_0008__210417_MtErie_Enterprise_IR_0008_out_frame",
        ]
        self.assertEqual(len({sequence_key(name) for name in names}), len(names))

    def test_image_paths_strip_hash_prefix_roboflow_suffix_and_frame(self) -> None:
        cases = {
            "/x/medium_crops/wisard/images/b89faac9cc574e44_200704_Baker_FLIR_IR_1__200704_baker__FLIR_1_ 0001.png": (
                "200704_baker_flir_1", 1,
            ),
            "/x/images/27ba949efd102dc3_003ccbb7241a_210417_MtErie_Enterprise_IR_0006_00140_jpeg.rf.5992008b_negative.png": (
                "210417_mterie_enterprise_ir_0006", 140,
            ),
            "/x/images/652364d2b425bcf7_220109_Baker_Enterprise_IR_2__DJI_0585 (1-10-2022 2-52-01 PM).mp4_00007.png": (
                "dji_0585", 7,
            ),
            "/x/images/004a095a9dbc6e4e_89b2d9880353_200704_baker_FLIR_2_-0750_jpg.rf.a1cdae57_negative.png": (
                "200704_baker_flir_2", 750,
            ),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(image_sequence_key(path), expected)


def write_dataset(root: Path, name: str, splits: dict[str, list[str]]) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    raw = {"path": str(folder), "nc": 1, "names": {0: "person"}}
    for split, images in splits.items():
        (folder / f"{split}.txt").write_text("\n".join(images) + "\n", encoding="utf-8")
        raw[split] = str(folder / f"{split}.txt")
    (folder / "data.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    return folder / "data.yaml"


class FindLeaksTests(unittest.TestCase):
    def test_cross_generation_leak_is_reported_and_clean_split_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            train = write_dataset(root, "old", {
                "train": [
                    f"/old/images/aaaaaaaaaaaaaaaa_210417_MtErie_Enterprise_IR_0008_out_frame_{index:05d}_jpg.rf.ff.png"
                    for index in range(3)
                ] + ["/old/images/DJI_0583-1-10-2022-2-51-48-PM-mp4_00001_jpg.rf.ee.png"],
            })
            evaluation = write_dataset(root, "new", {
                "val": [
                    f"/new/images/210417_MtErie_Enterprise_IR_0008__210417_MtErie_Enterprise_IR_0008_out_frame_ {index:04d}.png"
                    for index in range(1, 6)
                ],
                "test": ["/new/images/210924_FHL_Enterprise_IR_0408__DJI_0408.mp4_00001.png"],
            })
            report = find_leaks(train, evaluation, ("val", "test"), root)
            self.assertTrue(report.leaked)
            self.assertEqual(report.leaks["test"], [])
            (leak,) = report.leaks["val"]
            self.assertEqual(leak["sequence_key"], "210417_mterie_enterprise_ir_0008_out_frame")
            self.assertEqual((leak["eval_frames"], leak["train_frames"], leak["shared_frame_ids"]), (5, 3, 2))


class PortablePathTests(unittest.TestCase):
    def test_lists_recorded_on_another_machine_are_rebased(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "checkout"
            image = root / "AI" / "datasets" / "set" / "images" / "a_ 0001.png"
            image.parent.mkdir(parents=True)
            image.touch()
            self.assertEqual(rebase_repo_path("/elsewhere/vigil/AI/datasets/set/images/a_ 0001.png", root), image)
            fold = root / "AI" / "datasets" / "set" / "fold_0"
            fold.mkdir()
            (fold / "val.txt").write_text("/elsewhere/vigil/AI/datasets/set/images/a_ 0001.png\n", encoding="utf-8")
            (fold / "data.yaml").write_text(
                yaml.safe_dump({"path": "/elsewhere/vigil/AI/datasets/set/fold_0", "val": "/elsewhere/vigil/AI/datasets/set/fold_0/val.txt", "names": {0: "person"}}),
                encoding="utf-8",
            )
            rebased = portable_dataset_yaml(fold / "data.yaml", root, root / "cache")
            raw = yaml.safe_load(rebased.read_text(encoding="utf-8"))
            self.assertEqual(Path(raw["val"]).read_text(encoding="utf-8").strip(), str(image))


class BenchmarkAggregationTests(unittest.TestCase):
    def test_flagged_sequence_is_excluded_from_pooled_counts(self) -> None:
        def video(tp: int, fp: int, fn: int, tn: int, alerts: int) -> dict:
            return {
                "frame_metrics": {"tp_frames": tp, "fp_frames": fp, "fn_frames": fn, "tn_frames": tn},
                "temporal": {"smoothed": {"events": 1 if tp + fn else 0, "detected_events": 1 if tp else 0,
                                          "false_alert_episodes": alerts, "longest_miss_streak_frames": fn}},
            }

        report = {
            "person_metrics": {"map50": 0.5, "map50_95": 0.2},
            "per_video_metrics": {
                "210924_FHL_Enterprise_IR_0404__DJI_0404.mp4": video(8, 2, 2, 88, 3),
                "220109_Baker_Enterprise_IR_2__DJI_0585 (1-10-2022 2-52-01 PM).mp4": video(0, 90, 0, 10, 4),
            },
        }
        everything = summarize(report, set())
        excluded = summarize(report, {"dji_0585"})
        self.assertAlmostEqual(everything["specificity"], 98 / 190)
        self.assertAlmostEqual(excluded["specificity"], 88 / 90)
        self.assertEqual(excluded["false_alert_episodes"], 3)
        self.assertIsNone(excluded["map50"])
        self.assertEqual(everything["map50"], 0.5)

    def test_mean_std_handles_single_and_missing_values(self) -> None:
        self.assertIsNone(mean_std([0.5])["std"])
        self.assertEqual(mean_std([None, 0.5, 0.7])["n"], 2)
        self.assertAlmostEqual(mean_std([0.5, 0.7])["mean"], 0.6)


if __name__ == "__main__":
    unittest.main()
