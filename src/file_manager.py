from __future__ import annotations

import shutil
import os
from pathlib import Path
from typing import Callable

from src.config import (
    CATEGORY_REJECTED,
    CATEGORY_SELECTED,
    RAW_IMAGE_EXTENSIONS,
    STANDARD_IMAGE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
)

LogFunction = Callable[[str], None]


def ensure_output_directories(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for category in (CATEGORY_SELECTED, CATEGORY_REJECTED):
        (output_dir / category).mkdir(parents=True, exist_ok=True)


def find_supported_files(input_dir: Path) -> list[Path]:
    files, _ = discover_supported_files(input_dir)
    return files


def discover_supported_files(input_dir: Path, logger: LogFunction | None = None) -> tuple[list[Path], int]:
    log = logger or (lambda message: None)
    files: list[Path] = []
    skipped_count = 0

    def handle_walk_error(error: OSError) -> None:
        nonlocal skipped_count
        skipped_count += 1
        log(f"Atlandı: klasör okunamadı. Detay: {error}")

    for root, dirnames, filenames in os.walk(input_dir, onerror=handle_walk_error):
        dirnames[:] = [dirname for dirname in dirnames if dirname != "ErgeneAI_Output"]
        root_path = Path(root)
        for filename in filenames:
            path = root_path / filename
            try:
                if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(path)
                else:
                    skipped_count += 1
                    log(f"Atlandı: desteklenmeyen format: {path.name}")
            except OSError as exc:
                skipped_count += 1
                log(f"Atlandı: dosya bilgisi okunamadı: {path}. Detay: {exc}")

    return _prefer_standard_preview_files(files), skipped_count


def copy_to_category(source_path: Path, output_dir: Path, category: str) -> Path:
    target_dir = output_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = _build_safe_target_path(target_dir, source_path.name)
    shutil.copy2(source_path, target_path)
    _copy_matching_raw_sidecars(source_path, target_dir)
    return target_path


def _prefer_standard_preview_files(files: list[Path]) -> list[Path]:
    standard_stems = {
        (path.parent.resolve(), path.stem.lower())
        for path in files
        if path.suffix.lower() in STANDARD_IMAGE_EXTENSIONS
    }

    filtered = [
        path
        for path in files
        if not (
            path.suffix.lower() in RAW_IMAGE_EXTENSIONS
            and (path.parent.resolve(), path.stem.lower()) in standard_stems
        )
    ]
    return sorted(filtered)


def _copy_matching_raw_sidecars(source_path: Path, target_dir: Path) -> None:
    if source_path.suffix.lower() not in STANDARD_IMAGE_EXTENSIONS:
        return

    for raw_extension in RAW_IMAGE_EXTENSIONS:
        raw_path = source_path.with_suffix(raw_extension)
        if not raw_path.exists() or not raw_path.is_file():
            continue

        target_path = _build_safe_target_path(target_dir, raw_path.name)
        shutil.copy2(raw_path, target_path)


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
