from __future__ import annotations
import sys

import os
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

import logging

# Loglama yapılandırması
app_data_root = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "ErgeneAI"
log_dir = app_data_root / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=log_dir / "app_debug.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("ErgeneAI")

from src.cleanup import start_cleanup_service
from src.config import (
    CATEGORY_REJECTED,
    CATEGORY_SELECTED,
    WEB_UPLOAD_EXTENSIONS,
)
from src.database import Job, PhotoResult, SessionLocal, get_db, init_db
from src.file_manager import ensure_output_directories
from src.ai_settings import load_ai_settings, public_ai_settings, save_ai_settings
from src.ai_scorer import AIPhotoScore, AIPhotoScorer
from src.pipeline import CullingResult, process_culling
from src.report import write_reports

load_dotenv()
init_db()

def get_resource_path(relative_path):
    """ PyInstaller paketlemesi içinde dosyaların yolunu bulur. """
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent / relative_path

# Sabit kaynak klasörleri
TEMPLATES_DIR = get_resource_path("templates")
STATIC_DIR = get_resource_path("static")
RUNS_DIR = app_data_root / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Fotoğraf Ayıklama Sistemi")


class AISettingsRequest(BaseModel):
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    enabled: bool | None = None
    clear_api_key: bool = False


class PhotoMetadataRequest(BaseModel):
    star_rating: int | None = None
    color_label: str | None = None
    favorite: bool | None = None

@app.on_event("startup")
async def startup_event():
    logger.info("Uygulama başlatıldı.")
    start_cleanup_service()

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/runs", StaticFiles(directory=str(RUNS_DIR)), name="runs")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "error": None,
            "ai_settings": public_ai_settings(),
        },
    )


@app.get("/settings/ai")
async def get_ai_settings():
    return public_ai_settings(load_ai_settings())


@app.post("/settings/ai")
async def update_ai_settings(payload: AISettingsRequest):
    api_key = payload.api_key
    if api_key is not None and not api_key.strip():
        api_key = None

    settings = save_ai_settings(
        api_key=api_key,
        model=payload.model,
        base_url=payload.base_url,
        enabled=payload.enabled,
        clear_api_key=payload.clear_api_key,
    )
    return {"status": "saved", **public_ai_settings(settings)}


@app.post("/process-local", response_class=HTMLResponse)
async def process_local_path(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    logger.info("process-local isteği alındı.")
    try:
        # Yerel klasör yolu formdan veya JSON gövdeden gelebilir.
        source_path = await _read_local_path(request)
        logger.info(f"Hedef klasör yolu: {source_path}")

        if not source_path or not Path(source_path).exists() or not Path(source_path).is_dir():
            logger.warning(f"Geçersiz yol: {source_path}")
            return _render_index_error(request, f"Geçersiz veya bulunamayan klasör yolu: {source_path}")
        
        input_dir = Path(source_path)
        job_id = str(uuid.uuid4())
        job_dir = RUNS_DIR / job_id
        output_dir = job_dir / "output"
        zips_dir = output_dir / "zips"
        thumbnails_dir = job_dir / "thumbnails"
        local_export_dir = _build_local_export_dir(input_dir)

        ensure_output_directories(output_dir)
        zips_dir.mkdir(parents=True, exist_ok=True)
        thumbnails_dir.mkdir(parents=True, exist_ok=True)

        new_job = Job(
            id=job_id,
            status="processing",
            message=f"Yerel klasör analiz ediliyor: {source_path}",
            total_count=0,
            local_output_dir=str(local_export_dir),
        )
        db.add(new_job)
        db.commit()

        background_tasks.add_task(
            _run_culling_job,
            job_id,
            input_dir,
            output_dir,
            zips_dir,
            0,
            str(request.base_url).rstrip("/"),
            thumbnails_dir,
            local_export_dir,
        )
        logger.info(f"Yerel iş başlatıldı. Job ID: {job_id}")

        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "job_id": job_id,
                "job_status": "processing",
                "message": "Yerel tarama başladı. Dosyalar yerinde analiz ediliyor.",
                "summary": {"total": 0, "selected": 0, "rejected": 0, "skipped": 0},
                "selected_items": [],
                "rejected_items": [],
                "log_lines": [],
                "error": "",
            },
        )
    except Exception as exc:
        logger.error(f"process-local hatası: {exc}", exc_info=True)
        return _render_index_error(request, "Yerel klasör işlenirken beklenmeyen bir hata oluştu.")

@app.post("/process", response_class=HTMLResponse)
async def process_uploads(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    logger.info("process (upload) isteği alındı.")
    try:
        if not files or all(not file.filename for file in files):
            logger.warning("Dosya seçilmeden yükleme denendi.")
            return _render_index_error(request, "Lütfen en az bir fotoğraf veya klasör seçin.")

        job_id = str(uuid.uuid4())
        job_dir = RUNS_DIR / job_id
        input_dir = job_dir / "input"
        output_dir = job_dir / "output"
        zips_dir = output_dir / "zips"
        thumbnails_dir = job_dir / "thumbnails"

        input_dir.mkdir(parents=True, exist_ok=True)
        ensure_output_directories(output_dir)
        zips_dir.mkdir(parents=True, exist_ok=True)
        thumbnails_dir.mkdir(parents=True, exist_ok=True)

        saved_count, unsupported_count = await _save_supported_uploads(files, input_dir)
        logger.info(f"Yükleme tamamlandı. Kaydedilen: {saved_count}, Desteklenmeyen: {unsupported_count}")

        if saved_count == 0:
            return _render_index_error(request, "Desteklenen fotoğraf bulunamadı.")

        new_job = Job(
            id=job_id,
            status="processing",
            message="Fotoğraflar analiz ediliyor...",
            total_count=saved_count
        )
        db.add(new_job)
        db.commit()

        background_tasks.add_task(
            _run_culling_job, job_id, input_dir, output_dir, zips_dir, unsupported_count, str(request.base_url).rstrip("/"), thumbnails_dir
        )
        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "job_id": job_id,
                "job_status": "processing",
                "message": "İşlem başladı. Fotoğraflar arka planda analiz ediliyor.",
                "summary": {"total": saved_count, "selected": 0, "rejected": 0, "skipped": unsupported_count},
                "selected_items": [],
                "rejected_items": [],
                "log_lines": [],
                "error": "",
            },
        )
    except Exception as exc:
        logger.error(f"process hatası: {exc}", exc_info=True)
        return _render_index_error(request, "Yükleme sırasında bir hata oluştu.")


@app.get("/result/{job_id}", response_class=HTMLResponse)
async def result_page(request: Request, job_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "error": "İstenen işlem bulunamadı.",
            },
            status_code=404,
        )

    photos = db.query(PhotoResult).filter(PhotoResult.job_id == job_id).all()
    selected_items = [p for p in photos if p.category == CATEGORY_SELECTED]
    rejected_items = [p for p in photos if p.category == CATEGORY_REJECTED]

    summary = {
        "total": job.total_count,
        "selected": job.selected_count,
        "rejected": job.rejected_count,
        "skipped": job.skipped_count
    }
    log_lines = [line for line in (job.error_log or "").splitlines() if line.strip()]

    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "job_id": job_id,
            "job_status": job.status,
            "message": job.message,
            "summary": summary,
            "selected_items": selected_items,
            "rejected_items": rejected_items,
            "log_lines": log_lines,
            "error": "",
        },
    )


@app.get("/photo/{job_id}/{photo_id}/image")
async def photo_image(
    job_id: str,
    photo_id: int,
    variant: str = "thumb",
    db: Session = Depends(get_db),
):
    if not _is_valid_job_id(job_id):
        raise HTTPException(status_code=404, detail="İşlem bulunamadı.")

    photo = db.query(PhotoResult).filter(PhotoResult.id == photo_id, PhotoResult.job_id == job_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Fotoğraf bulunamadı.")

    image_path = _resolve_photo_asset_path(job_id, photo, variant)
    if not image_path:
        raise HTTPException(status_code=404, detail="Fotoğraf önizlemesi bulunamadı.")

    return FileResponse(path=image_path)


@app.post("/toggle-photo/{job_id}/{photo_id}")
async def toggle_photo(job_id: str, photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(PhotoResult).filter(PhotoResult.id == photo_id, PhotoResult.job_id == job_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Fotoğraf bulunamadı.")

    job = db.query(Job).filter(Job.id == job_id).first()
    
    old_category = photo.category
    new_category = CATEGORY_REJECTED if old_category == CATEGORY_SELECTED else CATEGORY_SELECTED
    
    old_path = RUNS_DIR / job_id / photo.relative_path if photo.relative_path else Path(photo.original_path or "")
    original_path = Path(photo.original_path or "")
    if not old_path.exists() and original_path.exists():
        old_path = original_path
    new_dir = RUNS_DIR / job_id / "output" / new_category
    new_path = _build_safe_input_path(new_dir, photo.filename)
    
    # Eğer dosya runs içindeyse taşı, değilse (yerel analizse) seçilenlere kopyala
    if old_path.exists():
        new_dir.mkdir(parents=True, exist_ok=True)
        # Eğer kaynak dosya 'runs' içindeyse gerçek bir taşıma (move) yap
        try:
            old_path.resolve().relative_to(RUNS_DIR.resolve())
            shutil.move(str(old_path), str(new_path))
        except ValueError:
            # Kaynak dosya dışarıdaysa (yerel), yeni kategori SEÇİLEN ise kopyala, ELENEN ise sil
            if new_category == CATEGORY_SELECTED:
                shutil.copy2(str(old_path), str(new_path))
            else:
                # Elenenlere taşınan yerel dosya; çıktı klasöründeki kopyayı sil
                # photo.relative_path şu an seçilenler klasöründeki kopyayı gösteriyor olmalı
                current_copy = RUNS_DIR / job_id / photo.relative_path
                if current_copy.exists() and current_copy.is_file():
                    current_copy.unlink()
                # Yeni yol artık orijinal yolu gösterir (kopyası yok)
                new_path = Path(photo.original_path)

        # Veritabanındaki yolu güncelle
        try:
            photo.relative_path = str(new_path.relative_to(RUNS_DIR / job_id)).replace("\\", "/")
        except ValueError:
            # Eğer dosya runs dışında kaldıysa (yerel elenen), path'i sahte bir çıktı yolu olarak bırak
            photo.relative_path = f"output/{new_category}/{photo.filename}"
        
    photo.category = new_category
    photo.ai_analysis_candidate = 1 if new_category == CATEGORY_SELECTED else 0
    if new_category == CATEGORY_SELECTED:
        job.selected_count += 1
        job.rejected_count -= 1
    else:
        job.selected_count -= 1
        job.rejected_count += 1
        
    _write_job_reports_from_db(job_id, db)
    db.commit()
    
    return {"status": "success", "new_category": new_category}


@app.post("/photo/{job_id}/{photo_id}/metadata")
async def update_photo_metadata(
    job_id: str,
    photo_id: int,
    payload: PhotoMetadataRequest,
    db: Session = Depends(get_db),
):
    if not _is_valid_job_id(job_id):
        raise HTTPException(status_code=404, detail="İşlem bulunamadı.")

    photo = db.query(PhotoResult).filter(PhotoResult.id == photo_id, PhotoResult.job_id == job_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Fotoğraf bulunamadı.")

    _apply_photo_metadata_update(photo, payload)
    _write_job_reports_from_db(job_id, db)
    db.commit()
    return {
        "status": "saved",
        "photo_id": photo.id,
        "star_rating": int(photo.star_rating or 0),
        "color_label": photo.color_label or "",
        "favorite": bool(photo.favorite),
    }


@app.get("/download/{job_id}/{download_type}", name="download_result", response_model=None)
async def download_result(request: Request, job_id: str, download_type: str):
    if not _is_valid_job_id(job_id):
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "error": "İstenen işlem numarası geçerli değil.",
            },
            status_code=404,
        )

    if download_type in ["selected", "rejected"]:
        job_dir = RUNS_DIR / job_id
        output_dir = job_dir / "output"
        zips_dir = output_dir / "zips"
        zips_dir.mkdir(parents=True, exist_ok=True)
        _create_result_zips(output_dir, zips_dir)

    file_map = {
        "selected": RUNS_DIR / job_id / "output" / "zips" / "selected.zip",
        "rejected": RUNS_DIR / job_id / "output" / "zips" / "rejected.zip",
        "csv": RUNS_DIR / job_id / "output" / "report.csv",
        "json": RUNS_DIR / job_id / "output" / "report.json",
    }

    target_path = file_map.get(download_type)

    if target_path is None or not target_path.exists():
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "error": "İstenen indirme dosyası mevcut değil.",
            },
            status_code=404,
        )

    return FileResponse(
        path=target_path,
        filename=target_path.name,
        media_type="application/octet-stream",
    )


@app.post("/open-folder/{job_id}/{folder_kind}")
async def open_output_folder(job_id: str, folder_kind: str, db: Session = Depends(get_db)):
    if not _is_valid_job_id(job_id):
        raise HTTPException(status_code=404, detail="İşlem bulunamadı.")

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="İşlem bulunamadı.")

    folder_path = _resolve_output_folder_path(job_id, folder_kind, job.local_output_dir)
    if not folder_path:
        raise HTTPException(status_code=404, detail="Klasör bulunamadı.")

    if hasattr(os, "startfile"):
        os.startfile(str(folder_path))  # type: ignore[attr-defined]
        return {"status": "opened", "path": str(folder_path)}

    return {"status": "available", "path": str(folder_path)}


@app.post("/ai-analyze/{job_id}")
async def analyze_job_with_ai(job_id: str, db: Session = Depends(get_db)):
    if not _is_valid_job_id(job_id):
        raise HTTPException(status_code=404, detail="İşlem bulunamadı.")

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="İşlem bulunamadı.")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="AI analiz için işlem tamamlanmış olmalı.")

    scorer = AIPhotoScorer.from_env()
    if not scorer.enabled:
        return {
            "status": "disabled",
            "message": "AI analiz kapalı veya API key tanımlı değil. Ana sayfadaki AI API Ayarları bölümünden ekleyebilirsiniz.",
            "analyzed": 0,
            "failed": 0,
        }

    max_photos = _read_int_env("AI_MAX_PHOTOS_PER_JOB", 40)
    photos = (
        db.query(PhotoResult)
        .filter(PhotoResult.job_id == job_id, PhotoResult.ai_analysis_candidate == 1)
        .order_by(PhotoResult.final_score.desc())
        .limit(max_photos)
        .all()
    )

    analyzed_count = 0
    failed_count = 0
    for photo in photos:
        image_path = _resolve_photo_asset_path(job_id, photo, "full")
        if not image_path:
            failed_count += 1
            continue

        try:
            score = scorer.score_photo(image_path)
            _apply_ai_score_to_photo(photo, score)
            analyzed_count += 1
        except Exception as exc:
            failed_count += 1
            logger.warning(f"AI analiz atlandı: {photo.filename}. Detay: {exc}")

    job.message = f"AI analiz tamamlandı. Analiz edilen: {analyzed_count}, atlanan: {failed_count}."
    _write_job_reports_from_db(job_id, db)
    db.commit()
    return {"status": "completed", "analyzed": analyzed_count, "failed": failed_count}



async def _save_supported_uploads(
    files: list[UploadFile],
    input_dir: Path,
) -> tuple[int, int]:
    saved_count = 0
    unsupported_count = 0

    for upload in files:
        try:
            if not upload.filename:
                continue

            safe_name = _sanitize_filename(upload.filename)

            if Path(safe_name).suffix.lower() not in WEB_UPLOAD_EXTENSIONS:
                unsupported_count += 1
                logger.warning(f"Desteklenmeyen dosya formatı atlandı: {upload.filename}")
                continue

            target_path = _build_safe_input_path(input_dir, safe_name)

            # Daha hızlı ve güvenli dosya yazma
            with target_path.open("wb") as target_file:
                shutil.copyfileobj(upload.file, target_file)

            saved_count += 1
            logger.info(f"Dosya yüklendi: {safe_name}")
        except Exception as e:
            logger.error(f"Dosya kaydedilirken hata: {upload.filename} - {str(e)}")
            unsupported_count += 1
        finally:
            await upload.close()

    return saved_count, unsupported_count


def _sanitize_filename(filename: str) -> str:
    clean_name = Path(filename.replace("\\", "/")).name
    suffix = Path(clean_name).suffix.lower()
    stem = Path(clean_name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._")

    if not safe_stem:
        safe_stem = "foto"

    return f"{safe_stem}{suffix}"


def _build_safe_input_path(input_dir: Path, filename: str) -> Path:
    candidate = input_dir / filename

    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1

    while True:
        numbered_candidate = input_dir / f"{stem}_{counter}{suffix}"
        if not numbered_candidate.exists():
            return numbered_candidate
        counter += 1


def _is_valid_job_id(job_id: str) -> bool:
    try:
        uuid.UUID(job_id)
    except ValueError:
        return False
    return True


def _resolve_photo_asset_path(job_id: str, photo: Any, variant: str = "thumb") -> Path | None:
    job_dir = RUNS_DIR / job_id
    candidates: list[str] = []

    if variant == "thumb" and getattr(photo, "thumbnail_path", ""):
        candidates.append(str(photo.thumbnail_path))

    if getattr(photo, "relative_path", ""):
        candidates.append(str(photo.relative_path))

    for candidate in candidates:
        path = (job_dir / candidate).resolve()
        try:
            path.relative_to(job_dir.resolve())
        except ValueError:
            continue

        if path.exists() and path.is_file():
            return path

    return None


def _resolve_output_folder_path(
    job_id: str,
    folder_kind: str,
    local_output_dir: str | None = None,
) -> Path | None:
    if local_output_dir:
        local_root = Path(local_output_dir).resolve()
        local_map = {
            "output": local_root,
            "selected": local_root / "Selected",
            "rejected": local_root / "Rejected",
        }
        local_path = local_map.get(folder_kind)
        if local_path is not None and local_path.exists() and local_path.is_dir():
            return local_path

    job_dir = (RUNS_DIR / job_id).resolve()
    folder_map = {
        "output": job_dir / "output",
        "selected": job_dir / "output" / CATEGORY_SELECTED,
        "rejected": job_dir / "output" / CATEGORY_REJECTED,
    }
    folder_path = folder_map.get(folder_kind)
    if folder_path is None:
        return None

    resolved = folder_path.resolve()
    try:
        resolved.relative_to(job_dir)
    except ValueError:
        return None

    if not resolved.exists() or not resolved.is_dir():
        return None

    return resolved


def _build_local_export_dir(input_dir: Path) -> Path:
    return input_dir / "ErgeneAI_Output"


def _mirror_output_to_local_export(output_dir: Path, local_export_dir: Path) -> None:
    local_export_dir.mkdir(parents=True, exist_ok=True)
    category_map = {
        CATEGORY_SELECTED: "Selected",
        CATEGORY_REJECTED: "Rejected",
    }

    for source_name, target_name in category_map.items():
        source_dir = output_dir / source_name
        target_dir = local_export_dir / target_name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        if source_dir.exists():
            shutil.copytree(source_dir, target_dir)
        else:
            target_dir.mkdir(parents=True, exist_ok=True)

    for report_name in ("report.csv", "report.json"):
        source_report = output_dir / report_name
        if source_report.exists():
            shutil.copy2(source_report, local_export_dir / report_name)


def _apply_ai_score_to_photo(photo: Any, score: AIPhotoScore) -> None:
    photo.ai_aesthetic_score = score.ai_aesthetic_score
    photo.ai_pose_score = score.ai_pose_score
    photo.ai_expression_note = score.ai_expression_note
    photo.ai_selection_reason = score.ai_selection_reason
    photo.ai_recommended = None if score.ai_recommended is None else int(score.ai_recommended)


def _apply_photo_metadata_update(photo: Any, payload: PhotoMetadataRequest) -> None:
    if payload.star_rating is not None:
        photo.star_rating = max(0, min(5, int(payload.star_rating)))

    if payload.color_label is not None:
        label = payload.color_label.strip().lower()
        photo.color_label = label if label in {"red", "yellow", "green", "blue"} else ""

    if payload.favorite is not None:
        photo.favorite = 1 if payload.favorite else 0


def _read_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _write_job_reports_from_db(job_id: str, db: Session) -> None:
    output_dir = RUNS_DIR / job_id / "output"
    photos = db.query(PhotoResult).filter(PhotoResult.job_id == job_id).all()
    records = [_photo_to_report_record(photo) for photo in photos]
    write_reports(records, output_dir)

    job = db.query(Job).filter(Job.id == job_id).first()
    if job and job.local_output_dir:
        _mirror_output_to_local_export(output_dir, Path(job.local_output_dir))


def _photo_to_report_record(photo: Any) -> dict[str, Any]:
    return {
        "filename": photo.filename,
        "original_path": photo.original_path,
        "category": photo.category,
        "final_score": photo.final_score,
        "blur_score": getattr(photo, "blur_score", ""),
        "brightness_score": getattr(photo, "brightness_score", ""),
        "contrast_score": getattr(photo, "contrast_score", ""),
        "face_count": getattr(photo, "face_count", ""),
        "reason": photo.reason,
        "similarity_group_id": photo.similarity_group_id,
        "similarity_group_size": getattr(photo, "similarity_group_size", 1),
        "best_in_group": bool(photo.best_in_group),
        "is_duplicate": bool(photo.is_duplicate),
        "duplicate_of": photo.duplicate_of,
        "ai_analysis_candidate": int(photo.ai_analysis_candidate or 0),
        "ai_aesthetic_score": photo.ai_aesthetic_score,
        "ai_pose_score": photo.ai_pose_score,
        "ai_expression_note": photo.ai_expression_note,
        "ai_selection_reason": photo.ai_selection_reason,
        "ai_recommended": photo.ai_recommended,
        "star_rating": getattr(photo, "star_rating", 0),
        "color_label": getattr(photo, "color_label", ""),
        "favorite": bool(getattr(photo, "favorite", 0)),
    }


async def _read_local_path(request: Request) -> str | None:
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            payload = await request.json()
            value = payload.get("path") if isinstance(payload, dict) else None
            return str(value).strip() if value else None
        except Exception:
            return None

    form_data = await request.form()
    value = form_data.get("path")
    return str(value).strip() if value else None


def _create_result_zips(output_dir: Path, zips_dir: Path) -> dict[str, Path]:
    zip_paths = {
        "selected": zips_dir / "selected.zip",
        "rejected": zips_dir / "rejected.zip",
    }

    _zip_directory(output_dir / CATEGORY_SELECTED, zip_paths["selected"], CATEGORY_SELECTED)
    _zip_directory(output_dir / CATEGORY_REJECTED, zip_paths["rejected"], CATEGORY_REJECTED)

    return zip_paths


def _zip_directory(source_dir: Path, zip_path: Path, root_name: str) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        if not source_dir.exists():
            return

        for file_path in sorted(source_dir.rglob("*")):
            if file_path.is_file():
                zip_file.write(file_path, Path(root_name) / file_path.relative_to(source_dir))


def _notify_n8n(
    base_url: str,
    job_id: str,
    result: CullingResult,
    zip_paths: dict[str, Path],
    input_dir: Path,
    output_dir: Path,
) -> str:
    webhook_url = os.getenv("N8N_WEBHOOK_URL", "").strip()

    if not webhook_url:
        return "n8n bildirimi yapılandırılmamış"

    payload = {
        "job_id": job_id,
        "status": "completed",
        "summary": {
            "total": result.summary.total,
            "selected": result.summary.selected,
            "rejected": result.summary.rejected,
            "skipped": result.summary.skipped,
        },
        "paths": {
            "input_dir": str(input_dir.resolve()),
            "output_dir": str(output_dir.resolve()),
            "selected_dir": str((output_dir / CATEGORY_SELECTED).resolve()),
            "rejected_dir": str((output_dir / CATEGORY_REJECTED).resolve()),
            "report_csv": str(result.csv_path.resolve()),
            "report_json": str(result.json_path.resolve()),
        },
        "downloads": {
            "selected_zip": f"{base_url}/download/{job_id}/selected",
            "rejected_zip": f"{base_url}/download/{job_id}/rejected",
        },
        "ai_preparation": {
            "enabled_now": False,
            "candidate_category": CATEGORY_SELECTED,
            "reserved_fields": [
                "ai_aesthetic_score",
                "ai_pose_score",
                "ai_expression_note",
                "ai_selection_reason",
                "ai_recommended",
            ],
        },
        "next_step": "Gelecek sürümde seçilen fotoğraflar n8n içinde OpenAI Vision ile analiz edilebilir.",
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return "n8n bildirimi gönderildi"
    except requests.RequestException as exc:
        print(f"Uyarı: n8n bildirimi başarısız oldu ama işlem tamamlandı. Detay: {exc}")
        return "n8n bildirimi başarısız oldu ama işlem tamamlandı"


def _run_culling_job(
    job_id: str,
    input_dir: Path,
    output_dir: Path,
    zips_dir: Path,
    unsupported_count: int,
    base_url: str,
    thumbnail_dir: Path | None = None,
    local_export_dir: Path | None = None,
) -> None:
    db = SessionLocal()
    job_logs: list[str] = []

    def job_logger(message: str) -> None:
        print(message)
        logger.info(message)
        if message.startswith("Atlandı") or "hata" in message.lower() or "başarısız" in message.lower():
            job_logs.append(message)

    try:
        result = process_culling(
            input_dir=input_dir,
            output_dir=output_dir,
            thumbnail_dir=thumbnail_dir,
            logger=job_logger,
            initial_skipped_count=unsupported_count,
        )
        _create_result_zips(output_dir, zips_dir)
        if local_export_dir is not None:
            _mirror_output_to_local_export(output_dir, local_export_dir)
        _notify_n8n(base_url, job_id, result, zip_paths={}, input_dir=input_dir, output_dir=output_dir)

        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = "completed"
        job.message = "Fotoğraflarınız hazır. En iyi kareler seçildi, gereksizler elendi."
        job.total_count = result.summary.total
        job.selected_count = result.summary.selected
        job.rejected_count = result.summary.rejected
        job.skipped_count = result.summary.skipped
        job.error_log = "\n".join(job_logs[-300:])
        if local_export_dir is not None:
            job.local_output_dir = str(local_export_dir)
        
        for record in result.records:
            t_path = record.get("thumbnail_path")
            t_rel_path = ""
            if t_path:
                # runs/{job_id}/thumbnails/name.jpg -> thumbnails/name.jpg
                t_rel_path = f"thumbnails/{Path(t_path).name}"

            copied_path_text = record.get("copied_path", "")
            output_relative_path = ""
            if copied_path_text:
                copied_path = Path(copied_path_text)
                try:
                    output_relative_path = str(copied_path.relative_to(output_dir.parent)).replace("\\", "/")
                except ValueError:
                    output_relative_path = f"output/{record['category']}/{copied_path.name}"

            photo = PhotoResult(
                job_id=job_id,
                filename=record["filename"],
                category=record["category"],
                final_score=record["final_score"],
                blur_score=record.get("blur_score"),
                brightness_score=record.get("brightness_score"),
                contrast_score=record.get("contrast_score"),
                face_count=record.get("face_count"),
                reason=record["reason"],
                original_path=record["original_path"],
                relative_path=output_relative_path,
                thumbnail_path=t_rel_path,
                ai_analysis_candidate=1 if record.get("ai_analysis_candidate") else 0,
                ai_aesthetic_score=record.get("ai_aesthetic_score"),
                ai_pose_score=record.get("ai_pose_score"),
                ai_expression_note=record.get("ai_expression_note", ""),
                ai_selection_reason=record.get("ai_selection_reason", ""),
                ai_recommended=record.get("ai_recommended"),
                similarity_group_id=record.get("similarity_group_id", ""),
                similarity_group_size=record.get("similarity_group_size", 1),
                best_in_group=1 if record.get("best_in_group", True) else 0,
                is_duplicate=1 if record.get("is_duplicate") else 0,
                duplicate_of=record.get("duplicate_of", ""),
                star_rating=record.get("star_rating", 0),
                color_label=record.get("color_label", ""),
                favorite=1 if record.get("favorite") else 0,
            )
            db.add(photo)
        
        db.commit()
    except Exception as exc:
        error_message = f"Arka plan işlemi başarısız oldu: {exc}"
        print(error_message)
        logger.error(error_message, exc_info=True)
        job_logs.append(error_message)
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.message = f"İşlem tamamlanamadı: {str(exc)}"
            job.error_log = "\n".join(job_logs[-300:])
            db.commit()
    finally:
        db.close()


def _render_index_error(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "error": message,
            "ai_settings": public_ai_settings(),
        },
        status_code=400,
    )
