from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


REPORT_COLUMNS = [
    "filename",
    "original_path",
    "category",
    "final_score",
    "blur_score",
    "brightness_score",
    "contrast_score",
    "face_count",
    "reason",
    "similarity_group_id",
    "similarity_group_size",
    "best_in_group",
    "is_duplicate",
    "duplicate_of",
    "ai_analysis_candidate",
    "ai_aesthetic_score",
    "ai_pose_score",
    "ai_expression_note",
    "ai_selection_reason",
    "ai_recommended",
    "star_rating",
    "color_label",
    "favorite",
]


def write_reports(records: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    csv_path = output_dir / "report.csv"
    json_path = output_dir / "report.json"
    report_records = [_prepare_record(record) for record in records]

    dataframe = pd.DataFrame(report_records, columns=REPORT_COLUMNS)
    dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(report_records, json_file, ensure_ascii=False, indent=2)

    return csv_path, json_path


def _prepare_record(record: dict[str, Any]) -> dict[str, Any]:
    return {column: record.get(column, "") for column in REPORT_COLUMNS}
