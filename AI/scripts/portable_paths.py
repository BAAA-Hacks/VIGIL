"""Rebase absolute VIGIL paths recorded on one machine onto another checkout."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

try:
    from AI.scripts.dataset_utils import SPLIT_KEYS, load_dataset_config
except ModuleNotFoundError:
    from AI.scripts.dataset_utils import SPLIT_KEYS, load_dataset_config  # type: ignore


REPO_MARKERS = ("datasets", "models", "checkpoints", "reports", "config")


def default_root() -> Path:
    """Repository root: $VIGIL_ROOT, else the checkout containing this file."""
    configured = os.environ.get("VIGIL_ROOT")
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[2]


def rebase_repo_path(path: str | Path, root: Path) -> Path:
    """Map ``<any prefix>/AI/<marker>/...`` onto ``<root>/AI/<marker>/...`` when missing."""
    candidate = Path(str(path)).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.exists():
        return candidate
    parts = candidate.parts
    for index in range(len(parts) - 2, -1, -1):
        if parts[index] == "AI" and parts[index + 1] in REPO_MARKERS:
            return root.joinpath(*parts[index:])
    return candidate


def portable_dataset_yaml(yaml_path: str | Path, root: Path, cache_dir: Path) -> Path:
    """Return a data.yaml whose split lists resolve on this machine.

    The original file is returned untouched when every listed image already exists.
    Otherwise rebased copies of the YAML and its .txt lists are written to ``cache_dir``.
    """
    source = rebase_repo_path(yaml_path, root)
    config = load_dataset_config(source)
    output = dict(config.raw)
    changed = False
    rewritten: dict[str, list[str]] = {}
    for split in SPLIT_KEYS:
        entry = config.raw.get(split)
        if entry is None:
            continue
        entries = entry if isinstance(entry, list) else [entry]
        resolved_entries = []
        for item in entries:
            item_path = rebase_repo_path(item if Path(str(item)).is_absolute() else config.root / str(item), root)
            if str(item_path) != str(item):
                changed = True
            if item_path.suffix.lower() == ".txt" and item_path.is_file():
                lines = [line.strip() for line in item_path.read_text(encoding="utf-8").splitlines()]
                images = [str(rebase_repo_path(line, root)) for line in lines if line and not line.startswith("#")]
                if images != [line for line in lines if line and not line.startswith("#")]:
                    changed = True
                rewritten[f"{split}_{len(resolved_entries)}"] = images
                resolved_entries.append(f"{split}_{len(resolved_entries)}.txt")
            else:
                resolved_entries.append(str(item_path))
        output[split] = resolved_entries if isinstance(entry, list) else resolved_entries[0]
    if not changed:
        return source
    cache_dir.mkdir(parents=True, exist_ok=True)
    for stem, images in rewritten.items():
        (cache_dir / f"{stem}.txt").write_text("\n".join(images) + "\n", encoding="utf-8")
    for split in SPLIT_KEYS:
        value = output.get(split)
        if isinstance(value, list):
            output[split] = [str(cache_dir / item) if item.endswith(".txt") and "/" not in item else item for item in value]
        elif isinstance(value, str) and value.endswith(".txt") and "/" not in value:
            output[split] = str(cache_dir / value)
    output["path"] = str(cache_dir)
    output["vigil_rebased_from"] = str(source)
    target = cache_dir / "data.yaml"
    target.write_text(yaml.safe_dump(output, sort_keys=False), encoding="utf-8")
    return target
