from __future__ import annotations

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
from sqlalchemy.orm import Session

from src.cleanup import start_cleanup_service
from src.config import (
    CATEGORY_REJECTED,
    CATEGORY_SELECTED,
    WEB_UPLOAD_EXTENSIONS,
)
from src.database import Job, PhotoResult, SessionLocal, get_db, init_db
from src.file_manager import ensure_output_directories
from src.pipeline import CullingResult, process_culling

load_dotenv()
init_db()

app = FastAPI(title="AI Fotoğraf Ayıklama Sistemi")

@app.on_event("startup")
async def startup_event():
    start_cleanup_service()

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

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
        },
    )


from pydantic import BaseModel

class LocalPathRequest(BaseModel):
    path: str

@app.post("/process-local", response_class=HTMLResponse)
async def process_local_path(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: LocalPathRequest = None,
    db: Session = Depends(get_db),
    path: str = None # Fallback for form data
) -> HTMLResponse:
    # Hem JSON hem Form verisini destekle
    source_path = path or (payload.path if payload else None)
    
    if not source_path:
        # Formdan gelmiş olabilir
        form_data = await request.form()
        source_path = form_data.get("path")

    if not source_path or not Path(source_path).exists() or not Path(source_path).is_dir():
        return _render_index_error(request, f"Geçersiz veya bulunamayan klasör yolu: {source_path}")

    input_dir = Path(source_path)
    job_id = str(uuid.uuid4())
    job_dir = RUNS_DIR / job_id
    output_dir = job_dir / "output"
    zips_dir = output_dir / "zips"
    thumbnails_dir = job_dir / "thumbnails"

    try:
        ensure_output_directories(output_dir)
        zips_dir.mkdir(parents=True, exist_ok=True)
        thumbnails_dir.mkdir(parents=True, exist_ok=True)

        # Create database entry
        new_job = Job(
            id=job_id,
            status="processing",
            message=f"Yerel klasör analiz ediliyor: {source_path}",
            total_count=0 # Analiz sırasında güncellenecek
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
            thumbnails_dir
        )

        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "job_id": job_id,
                "job_status": "processing",
                "message": "Yerel tarama başladı. Dosyalar kopyalanmadan yerinde analiz ediliyor.",
                "summary": {"total": 0, "selected": 0, "rejected": 0, "skipped": 0},
                "selected_items": [],
                "rejected_items": [],
                "error": "",
            },
        )
    except Exception as exc:
        print(f"Yerel işlem başarısız oldu: {exc}")
        return _render_index_error(request, "Yerel klasör işlenirken bir hata oluştu.")


@app.post("/process", response_class=HTMLResponse)
async def process_uploads(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if not files or all(not file.filename for file in files):
        return _render_index_error(request, "Lütfen en az bir fotoğraf veya klasör seçin.")

    job_id = str(uuid.uuid4())
    job_dir = RUNS_DIR / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    zips_dir = output_dir / "zips"
    thumbnails_dir = job_dir / "thumbnails"

    try:
        input_dir.mkdir(parents=True, exist_ok=True)
        ensure_output_directories(output_dir)
        zips_dir.mkdir(parents=True, exist_ok=True)
        thumbnails_dir.mkdir(parents=True, exist_ok=True)

        saved_count, unsupported_count = await _save_supported_uploads(files, input_dir)

        if saved_count == 0:
            return _render_index_error(
                request,
                "Yüklenen dosyalar arasında desteklenen fotoğraf bulunamadı.",
            )

        new_job = Job(
            id=job_id,
            status="processing",
            message="İşlem başladı. Fotoğraflar arka planda analiz ediliyor.",
            total_count=saved_count
        )
        db.add(new_job)
        db.commit()

        background_tasks.add_task(
            _run_culling_job,
            job_id,
            input_dir,
            output_dir,
            zips_dir,
            unsupported_count,
            str(request.base_url).rstrip("/"),
            thumbnails_dir
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
                "error": "",
            },
        )
    except Exception as exc:
        print(f"Web işlemi başarısız oldu: {exc}")
        return _render_index_error(
            request,
            "İşlem sırasında beklenmeyen bir hata oluştu. Lütfen dosyaları kontrol edip tekrar deneyin.",
        )


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
            "error": "",
        },
    )


@app.post("/toggle-photo/{job_id}/{photo_id}")
async def toggle_photo(job_id: str, photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(PhotoResult).filter(PhotoResult.id == photo_id, PhotoResult.job_id == job_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Fotoğraf bulunamadı.")

    job = db.query(Job).filter(Job.id == job_id).first()
    
    old_category = photo.category
    new_category = CATEGORY_REJECTED if old_category == CATEGORY_SELECTED else CATEGORY_SELECTED
    
    old_path = RUNS_DIR / job_id / "output" / old_category / photo.filename
    new_dir = RUNS_DIR / job_id / "output" / new_category
    new_path = new_dir / photo.filename
    
    if old_path.exists():
        new_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
        
    photo.category = new_category
    if new_category == CATEGORY_SELECTED:
        job.selected_count += 1
        job.rejected_count -= 1
    else:
        job.selected_count -= 1
        job.rejected_count += 1
        
    db.commit()
    
    return {"status": "success", "new_category": new_category}


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


async def _save_supported_uploads(
    files: list[UploadFile],
    input_dir: Path,
) -> tuple[int, int]:
    saved_count = 0
    unsupported_count = 0

    for upload in files:
        try:
            if not upload.filename:
                unsupported_count += 1
                continue

            safe_name = _sanitize_filename(upload.filename)

            if Path(safe_name).suffix.lower() not in WEB_UPLOAD_EXTENSIONS:
                unsupported_count += 1
                continue

            target_path = _build_safe_input_path(input_dir, safe_name)

            with target_path.open("wb") as target_file:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    target_file.write(chunk)

            saved_count += 1
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
        "next_step": "OpenAI Vision enhancement can analyze selected and eliminated images.",
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
) -> None:
    db = SessionLocal()
    try:
        result = process_culling(
            input_dir=input_dir,
            output_dir=output_dir,
            thumbnail_dir=thumbnail_dir,
            logger=print,
            initial_skipped_count=unsupported_count,
        )
        _create_result_zips(output_dir, zips_dir)
        _notify_n8n(base_url, job_id, result, zip_paths={}, input_dir=input_dir, output_dir=output_dir)

        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = "completed"
        job.message = "Fotoğraflarınız hazır. En iyi kareler seçildi, gereksizler elendi."
        job.total_count = result.summary.total
        job.selected_count = result.summary.selected
        job.rejected_count = result.summary.rejected
        job.skipped_count = result.summary.skipped
        
        for record in result.records:
            t_path = record.get("thumbnail_path")
            t_rel_path = ""
            if t_path:
                # runs/{job_id}/thumbnails/name.jpg -> thumbnails/name.jpg
                t_rel_path = f"thumbnails/{Path(t_path).name}"

            photo = PhotoResult(
                job_id=job_id,
                filename=record["filename"],
                category=record["category"],
                final_score=record["final_score"],
                reason=record["reason"],
                relative_path=f"output/{record['category']}/{record['filename']}",
                thumbnail_path=t_rel_path
            )
            db.add(photo)
        
        db.commit()
    except Exception as exc:
        print(f"Arka plan işlemi başarısız oldu: {exc}")
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.message = f"İşlem tamamlanamadı: {str(exc)}"
            db.commit()
    finally:
        db.close()


def _render_index_error(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "error": message,
        },
        status_code=400,
    )
