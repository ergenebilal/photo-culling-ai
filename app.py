from __future__ import annotations

import os
import re
import uuid
import zipfile
from pathlib import Path
from threading import Lock
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import (
    CATEGORY_REJECTED,
    CATEGORY_SELECTED,
    WEB_UPLOAD_EXTENSIONS,
)
from src.file_manager import ensure_output_directories
from src.pipeline import CullingResult, process_culling

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="AI Fotoğraf Ayıklama Sistemi")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = Lock()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "error": None,
        },
    )


@app.post("/process", response_class=HTMLResponse)
async def process_uploads(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
) -> HTMLResponse:
    if not files or all(not file.filename for file in files):
        return _render_index_error(request, "Lütfen en az bir fotoğraf veya klasör seçin.")

    job_id = str(uuid.uuid4())
    job_dir = RUNS_DIR / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    zips_dir = output_dir / "zips"

    try:
        input_dir.mkdir(parents=True, exist_ok=True)
        ensure_output_directories(output_dir)
        zips_dir.mkdir(parents=True, exist_ok=True)

        saved_count, unsupported_count = await _save_supported_uploads(files, input_dir)

        if saved_count == 0:
            return _render_index_error(
                request,
                "Yüklenen dosyalar arasında desteklenen fotoğraf bulunamadı.",
            )

        _set_job_state(
            job_id,
            {
                "status": "processing",
                "message": "İşlem başladı. Fotoğraflar arka planda analiz ediliyor.",
                "summary": None,
                "selected_items": [],
                "rejected_items": [],
                "error": "",
            },
        )
        background_tasks.add_task(
            _run_culling_job,
            job_id,
            input_dir,
            output_dir,
            zips_dir,
            unsupported_count,
            str(request.base_url).rstrip("/"),
        )

        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "job_id": job_id,
                "job_status": "processing",
                "message": "İşlem başladı. Fotoğraflar arka planda analiz ediliyor.",
                "summary": None,
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
async def result_page(request: Request, job_id: str) -> HTMLResponse:
    job_state = _get_job_state(job_id)

    if not job_state:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "error": "İstenen işlem bulunamadı.",
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "job_id": job_id,
            "job_status": job_state["status"],
            "message": job_state["message"],
            "summary": job_state["summary"],
            "selected_items": job_state["selected_items"],
            "rejected_items": job_state["rejected_items"],
            "error": job_state["error"],
        },
    )


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
) -> None:
    try:
        result = process_culling(
            input_dir=input_dir,
            output_dir=output_dir,
            logger=print,
            initial_skipped_count=unsupported_count,
        )
        zip_paths = _create_result_zips(output_dir, zips_dir)
        _notify_n8n(base_url, job_id, result, zip_paths, input_dir, output_dir)

        _set_job_state(
            job_id,
            {
                "status": "completed",
                "message": "Fotoğraflarınız hazır. En iyi kareler seçildi, gereksizler elendi.",
                "summary": result.summary,
                "selected_items": _build_result_items(result.records, CATEGORY_SELECTED),
                "rejected_items": _build_result_items(result.records, CATEGORY_REJECTED),
                "error": "",
            },
        )
    except Exception as exc:
        print(f"Arka plan işlemi başarısız oldu: {exc}")
        _set_job_state(
            job_id,
            {
                "status": "failed",
                "message": "İşlem tamamlanamadı.",
                "summary": None,
                "selected_items": [],
                "rejected_items": [],
                "error": "Fotoğraflar işlenirken beklenmeyen bir hata oluştu.",
            },
        )


def _build_result_items(records: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    items = [
        {
            "filename": record["filename"],
            "final_score": record["final_score"],
            "reason": record["reason"],
        }
        for record in records
        if record["category"] == category
    ]
    return sorted(items, key=lambda item: item["final_score"], reverse=True)


def _set_job_state(job_id: str, state: dict[str, Any]) -> None:
    with JOBS_LOCK:
        JOBS[job_id] = state


def _get_job_state(job_id: str) -> dict[str, Any] | None:
    with JOBS_LOCK:
        return JOBS.get(job_id)


def _render_index_error(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "error": message,
        },
        status_code=400,
    )
