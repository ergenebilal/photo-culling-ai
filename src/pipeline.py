from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.analyzer import ImageAnalyzer
from src.classifier import classify_photo
from src.config import CATEGORY_REJECTED, CATEGORY_SELECTED
from src.file_manager import copy_to_category, ensure_output_directories, find_supported_files
from src.report import write_reports
from src.similarity import mark_similar_groups


LogFunction = Callable[[str], None]
DEFAULT_WORKER_COUNT = max(4, min(os.cpu_count() or 4, 8))


@dataclass(frozen=True)
class CullingSummary:
    total: int
    selected: int
    rejected: int
    duplicates: int
    skipped: int


@dataclass(frozen=True)
class CullingResult:
    records: list[dict[str, Any]]
    summary: CullingSummary
    csv_path: Path
    json_path: Path


def process_culling(
    input_dir: Path,
    output_dir: Path,
    thumbnail_dir: Path | None = None,
    logger: LogFunction | None = None,
    initial_skipped_count: int = 0,
    max_workers: int | None = None,
) -> CullingResult:
    log = logger or (lambda message: None)

    ensure_output_directories(output_dir)
    image_paths = find_supported_files(input_dir)
    records: list[dict[str, Any]] = []
    skipped_count = initial_skipped_count

    log(f"Toplam {len(image_paths)} desteklenen dosya bulundu.")

    if not image_paths:
        csv_path, json_path = write_reports(records, output_dir)
        return CullingResult(
            records=records,
            summary=CullingSummary(
                total=0,
                selected=0,
                rejected=0,
                duplicates=0,
                skipped=0,
            ),
            csv_path=csv_path,
            json_path=json_path,
        )

    worker_count = max_workers or DEFAULT_WORKER_COUNT
    log(f"Paralel analiz başlatıldı. İşçi sayısı: {worker_count}")

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        future_map = {}
        for image_path in image_paths:
            # Thumbnail ismini güvenli hale getir
            t_name = f"{image_path.stem}_{uuid.uuid4().hex[:8]}.jpg"
            t_path = thumbnail_dir / t_name if thumbnail_dir else None
            future = executor.submit(
                _analyze_photo_worker, 
                str(image_path.resolve()), 
                str(t_path.resolve()) if t_path else None
            )
            future_map[future] = image_path

        for completed_count, future in enumerate(as_completed(future_map), start=1):
            image_path = future_map[future]
            log(f"[{completed_count}/{len(image_paths)}] Sonuç alındı: {image_path.name}")

            try:
                result = future.result()
            except Exception as exc:
                skipped_count += 1
                log(f"Atlandı: {image_path.name} işlenirken hata oluştu. Detay: {exc}")
                continue

            if not result["success"]:
                skipped_count += 1
                log(f"Atlandı: {image_path.name} analiz edilemedi. Detay: {result['error']}")
                continue

            records.append(result["record"])

    records = mark_similar_groups(records)
    _copy_records(records, output_dir, log)
    csv_path, json_path = write_reports(records, output_dir)
    summary = _build_summary(records, skipped_count)

    return CullingResult(
        records=records,
        summary=summary,
        csv_path=csv_path,
        json_path=json_path,
    )


def _build_summary(records: list[dict[str, Any]], skipped_count: int) -> CullingSummary:
    return CullingSummary(
        total=len(records),
        selected=sum(
            1
            for record in records
            if record["category"] == CATEGORY_SELECTED and not record["is_duplicate"]
        ),
        rejected=sum(1 for record in records if record["category"] == CATEGORY_REJECTED),
        duplicates=sum(1 for record in records if record["is_duplicate"]),
        skipped=skipped_count,
    )


def _copy_records(
    records: list[dict[str, Any]],
    output_dir: Path,
    log: LogFunction,
) -> None:
    # Runs klasörünün yerini tespit et (kopyalama kararı için)
    # output_dir: runs/{job_id}/output
    runs_dir = output_dir.parent.parent
    
    for record in records:
        source_path = Path(record["source_path"])
        if record["is_duplicate"]:
            record["category"] = CATEGORY_REJECTED
            record["reason"] = (
                "Fotoğraf benzer/tekrar kare olduğu için elenenler arasına alındı. "
                f"En iyi eşleşme: {record['duplicate_of']}."
            )

        target_category = record["category"]
        
        # Akıllı Kopyalama Kararı:
        # Sadece SEÇİLENLERİ veya UPLOAD edilen (runs içindeki) dosyaları kopyala.
        # Yerel klasördeki ELENENLERİ kopyalamıyoruz.
        should_copy = True
        if target_category == CATEGORY_REJECTED:
            try:
                # Dosya runs klasörü içindeyse (upload) kopyala, dışındaysa (yerel) atla.
                source_path.resolve().relative_to(runs_dir.resolve())
            except ValueError:
                should_copy = False
        
        if should_copy:
            copied_path = copy_to_category(source_path, output_dir, target_category)
            record["copied_path"] = str(copied_path.resolve())
            log(f"Kopyalandı: {record['category']}/{copied_path.name}")
        else:
            record["copied_path"] = str(source_path.resolve())
            log(f"Yerinde bırakıldı (Elenen): {source_path.name}")


def _analyze_photo_worker(image_path_text: str, thumbnail_path_text: str | None = None) -> dict[str, Any]:
    image_path = Path(image_path_text)
    thumbnail_path = Path(thumbnail_path_text) if thumbnail_path_text else None

    try:
        analyzer = ImageAnalyzer()
        analysis = analyzer.analyze(image_path, thumbnail_path=thumbnail_path)
        category, reason = classify_photo(analysis)
        return {
            "success": True,
            "record": {
                "filename": image_path.name,
                "original_path": str(image_path.resolve()),
                "source_path": str(image_path.resolve()),
                "copied_path": "",
                "category": category,
                "final_score": analysis.final_score,
                "blur_score": analysis.blur_score,
                "brightness_score": analysis.brightness_score,
                "contrast_score": analysis.contrast_score,
                "face_count": analysis.face_count,
                "reason": reason,
                "image_for_hash": analysis.pil_image,
                "similarity_group_id": "",
                "best_in_group": True,
                "is_duplicate": False,
                "duplicate_of": "",
                "thumbnail_path": thumbnail_path_text or "",
            },
            "error": "",
        }
    except Exception as exc:
        return {
            "success": False,
            "record": None,
            "error": str(exc),
        }
