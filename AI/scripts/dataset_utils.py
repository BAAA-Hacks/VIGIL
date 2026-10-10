from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import yaml


IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
SPLIT_KEYS = ("train", "val", "test")


@dataclass(frozen=True)
class DatasetConfig:
    yaml_path: Path
    root: Path
    raw: dict
    names: dict[int, str]


@dataclass(frozen=True)
class YoloBox:
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float


def load_dataset_config(path: str | Path) -> DatasetConfig:
    yaml_path = Path(path).expanduser().resolve()
    if not yaml_path.is_file():
        raise FileNotFoundError(f"Dataset YAML not found: {yaml_path}")
    with yaml_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Dataset YAML must contain a mapping: {yaml_path}")

    configured_root = raw.get("path")
    if configured_root:
        candidate = Path(str(configured_root)).expanduser()
        root = candidate if candidate.is_absolute() else yaml_path.parent / candidate
        root = root.resolve()
    else:
        root = yaml_path.parent.resolve()

    raw_names = raw.get("names", {})
    if isinstance(raw_names, list):
        names = {index: str(name) for index, name in enumerate(raw_names)}
    elif isinstance(raw_names, dict):
        names = {int(index): str(name) for index, name in raw_names.items()}
    else:
        raise ValueError("data.yaml 'names' must be a list or mapping")
    return DatasetConfig(yaml_path=yaml_path, root=root, raw=raw, names=names)


def find_data_yaml(dataset_root: str | Path) -> Path:
    root = Path(dataset_root).expanduser().resolve()
    if root.is_file() and root.suffix.lower() in {".yaml", ".yml"}:
        return root
    direct = [root / "data.yaml", root / "data.yml"]
    for candidate in direct:
        if candidate.is_file():
            return candidate
    matches = sorted((*root.rglob("data.yaml"), *root.rglob("data.yml")))
    if not matches:
        raise FileNotFoundError(f"No data.yaml or data.yml found below {root}")
    if len(matches) > 1:
        options = "\n  ".join(str(path) for path in matches)
        raise ValueError(f"Multiple dataset YAML files found; pass one explicitly:\n  {options}")
    return matches[0]


def _resolve_entry(config: DatasetConfig, entry: str | Path) -> Path:
    value = Path(str(entry)).expanduser()
    if value.is_absolute():
        return value.resolve()
    candidate = (config.root / value).resolve()
    if candidate.exists():
        return candidate

    # Roboflow exports commonly put data.yaml beside train/valid/test while
    # recording split paths as ../train/images. Recover that layout without
    # modifying the downloaded YAML.
    parts = list(value.parts)
    while parts and parts[0] in {".", ".."}:
        parts.pop(0)
    if parts:
        export_relative = (config.yaml_path.parent / Path(*parts)).resolve()
        if export_relative.exists():
            return export_relative
    return candidate


def resolved_dataset_yaml(config: DatasetConfig) -> dict:
    output = dict(config.raw)
    output.pop("download", None)
    output["path"] = str(config.yaml_path.parent.resolve())
    for split in SPLIT_KEYS:
        entry = config.raw.get(split)
        if entry is None:
            continue
        entries = entry if isinstance(entry, list) else [entry]
        resolved = [str(_resolve_entry(config, item)) for item in entries]
        output[split] = resolved if isinstance(entry, list) else resolved[0]
    return output


def write_resolved_dataset_yaml(config: DatasetConfig, path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(resolved_dataset_yaml(config), sort_keys=False), encoding="utf-8")
    return output


def _images_from_path(path: Path, config: DatasetConfig) -> list[Path]:
    if path.is_dir():
        return sorted(
            item.resolve()
            for item in path.rglob("*")
            if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
        )
    if path.is_file() and path.suffix.lower() == ".txt":
        images: list[Path] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            candidate = Path(line).expanduser()
            if not candidate.is_absolute():
                root_candidate = (config.root / candidate).resolve()
                list_candidate = (path.parent / candidate).resolve()
                candidate = root_candidate if root_candidate.exists() else list_candidate
            if candidate.suffix.lower() in IMAGE_SUFFIXES:
                images.append(candidate.resolve())
        return sorted(images)
    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
        return [path.resolve()]
    raise FileNotFoundError(f"Image split path does not exist or is unsupported: {path}")


def split_images(config: DatasetConfig, split: str) -> list[Path]:
    if split not in SPLIT_KEYS:
        raise ValueError(f"Unknown split {split!r}; expected one of {SPLIT_KEYS}")
    entry = config.raw.get(split)
    if entry is None:
        return []
    entries = entry if isinstance(entry, list) else [entry]
    images: list[Path] = []
    for item in entries:
        images.extend(_images_from_path(_resolve_entry(config, item), config))
    return sorted(dict.fromkeys(images))


def label_path_for_image(image_path: str | Path) -> Path:
    image = Path(image_path)
    parts = list(image.parts)
    image_indexes = [index for index, part in enumerate(parts) if part.lower() == "images"]
    if image_indexes:
        parts[image_indexes[-1]] = "labels"
        return Path(*parts).with_suffix(".txt")
    return image.with_suffix(".txt")


def source_frame_id(image_path: str | Path) -> tuple[str, int | None]:
    """Infer a source sequence/frame ID from Roboflow-exported WiSARD names."""
    base = Path(image_path).name.split(".rf.", maxsplit=1)[0]
    while re.match(r"^[0-9a-f]{12,16}_", base, flags=re.IGNORECASE):
        base = re.sub(r"^[0-9a-f]{12,16}_", "", base, count=1, flags=re.IGNORECASE)
    base = re.sub(r"_(?:jpg|jpeg|png)$", "", base, flags=re.IGNORECASE)
    match = re.match(r"^(.*?)[_-](\d+)$", base)
    return (match.group(1), int(match.group(2))) if match else (base, None)


def common_image_root(images: Iterable[Path]) -> Path:
    image_list = list(images)
    if not image_list:
        raise ValueError("Cannot determine an image root for an empty split")
    parents = [str(path.parent) for path in image_list]
    common = Path(__import__("os").path.commonpath(parents))
    return common.resolve()


def parse_label_line(line: str, *, source: str = "label") -> YoloBox:
    values = line.split()
    if len(values) != 5:
        raise ValueError(f"{source}: expected 5 values, found {len(values)}")
    try:
        class_value = float(values[0])
        coordinates = [float(value) for value in values[1:]]
    except ValueError as exc:
        raise ValueError(f"{source}: label contains a non-numeric value") from exc
    if not class_value.is_integer() or class_value < 0:
        raise ValueError(f"{source}: class ID must be a non-negative integer")
    if not all(__import__("math").isfinite(value) for value in coordinates):
        raise ValueError(f"{source}: coordinates must be finite")
    return YoloBox(int(class_value), *coordinates)


def read_yolo_labels(path: str | Path) -> tuple[list[YoloBox], list[str]]:
    label_path = Path(path)
    if not label_path.exists():
        return [], []
    boxes: list[YoloBox] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            boxes.append(parse_label_line(line, source=f"{label_path}:{line_number}"))
        except ValueError as exc:
            errors.append(str(exc))
    return boxes, errors


def box_is_normalized(box: YoloBox) -> bool:
    values = (box.x_center, box.y_center, box.width, box.height)
    if not all(0.0 <= value <= 1.0 for value in values):
        return False
    if box.width <= 0.0 or box.height <= 0.0:
        return False
    left = box.x_center - box.width / 2.0
    top = box.y_center - box.height / 2.0
    right = box.x_center + box.width / 2.0
    bottom = box.y_center + box.height / 2.0
    return left >= -1e-6 and top >= -1e-6 and right <= 1.0 + 1e-6 and bottom <= 1.0 + 1e-6


def format_yolo_box(box: YoloBox) -> str:
    return (
        f"{box.class_id} {box.x_center:.8f} {box.y_center:.8f} "
        f"{box.width:.8f} {box.height:.8f}"
    )


def chunks(items: list[Path], size: int) -> Iterator[list[Path]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def write_json(path: str | Path, payload: object) -> None:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
