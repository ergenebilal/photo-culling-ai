from __future__ import annotations

import shutil
from pathlib import Path

from src.config import (
    CATEGORY_REJECTED,
    CATEGORY_SELECTED,
    SUPPORTED_EXTENSIONS,
)


def ensure_output_directories(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for category in (CATEGORY_SELECTED, CATEGORY_REJECTED):
        (output_dir / category).mkdir(parents=True, exist_ok=True)


def find_supported_files(input_dir: Path) -> list[Path]:
    files = [
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files)


def copy_to_category(source_path: Path, output_dir: Path, category: str) -> Path:
    target_dir = output_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = _build_safe_target_path(target_dir, source_path.name)
    shutil.copy2(source_path, target_path)
    return target_path


def _build_safe_target_path(target_dir: Path, filename: str) -> Path:
    candidate = target_dir / filename

    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1

    while True:
        numbered_candidate = target_dir / f"{stem}_{counter}{suffix}"
        if not numbered_candidate.exists():
            return numbered_candidate
        counter += 1
