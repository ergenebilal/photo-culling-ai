from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread

from src.database import Job, PhotoResult, SessionLocal

# Ayarlar
CLEANUP_INTERVAL_SECONDS = 3600  # 1 saatte bir kontrol et
EXPIRATION_HOURS = 24           # 24 saatten eski işleri sil
RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CleanupService")


def start_cleanup_service():
    """Temizlik servisini ayrı bir thread'de başlatır."""
    thread = Thread(target=_cleanup_loop, daemon=True)
    thread.start()
    logger.info("Otomatik temizlik servisi başlatıldı (24 saatlik periyot).")


def _cleanup_loop():
    while True:
        try:
            _perform_cleanup()
        except Exception as e:
            logger.error(f"Temizlik sırasında hata: {e}")
        
        time.sleep(CLEANUP_INTERVAL_SECONDS)


def _perform_cleanup():
    db = SessionLocal()
    try:
        threshold = datetime.utcnow() - timedelta(hours=EXPIRATION_HOURS)
        
        # Süresi dolan işleri bul
        expired_jobs = db.query(Job).filter(Job.created_at < threshold).all()
        
        if not expired_jobs:
            return

        for job in expired_jobs:
            logger.info(f"Temizleniyor: Job ID {job.id} (Tarih: {job.created_at})")
            
            # 1. Fiziksel Dosyaları Sil
            job_dir = RUNS_DIR / job.id
            if job_dir.exists():
                shutil.rmtree(job_dir)
                logger.info(f"Dosyalar silindi: {job.id}")
            
            # 2. Veritabanı Kayıtlarını Sil
            db.query(PhotoResult).filter(PhotoResult.job_id == job.id).delete()
            db.delete(job)
            
        db.commit()
        logger.info(f"{len(expired_jobs)} eski iş başarıyla temizlendi.")
        
    finally:
        db.close()
