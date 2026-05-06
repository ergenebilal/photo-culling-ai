from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

# Windows AppData/Local/ErgeneAI klasörünü ayarla
app_data_root = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "ErgeneAI"
DB_PATH = app_data_root / "data" / "jobs.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True)
    status = Column(String, default="processing")
    message = Column(Text)
    error_log = Column(Text, default="")
    total_count = Column(Integer, default=0)
    selected_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    local_output_dir = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PhotoResult(Base):
    __tablename__ = "photo_results"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, index=True)
    filename = Column(String)
    category = Column(String)
    final_score = Column(Float)
    blur_score = Column(Float, nullable=True)
    brightness_score = Column(Float, nullable=True)
    contrast_score = Column(Float, nullable=True)
    face_count = Column(Integer, nullable=True)
    reason = Column(Text)
    original_path = Column(String)  # Dosyanın bilgisayardaki orijinal tam yolu
    relative_path = Column(String)  # runs/{job_id} klasörüne göre göreli sonuç yolu
    thumbnail_path = Column(String) # runs/{job_id} klasörüne göre göreli küçük görsel yolu
    ai_analysis_candidate = Column(Integer, default=0)
    ai_aesthetic_score = Column(Float, nullable=True)
    ai_pose_score = Column(Float, nullable=True)
    ai_expression_note = Column(Text, default="")
    ai_selection_reason = Column(Text, default="")
    ai_recommended = Column(Integer, nullable=True)
    similarity_group_id = Column(String, default="")
    similarity_group_size = Column(Integer, default=1)
    best_in_group = Column(Integer, default=1)
    is_duplicate = Column(Integer, default=0)
    duplicate_of = Column(String, default="")
    star_rating = Column(Integer, default=0)
    color_label = Column(String, default="")
    favorite = Column(Integer, default=0)


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_runtime_columns()


def _ensure_runtime_columns():
    # SQLite mevcut tabloları otomatik güncellemediği için eksik kolonlar güvenli eklenir.
    required_columns = {
        "jobs": {
            "error_log": "TEXT DEFAULT ''",
            "local_output_dir": "TEXT DEFAULT ''",
        },
        "photo_results": {
            "ai_analysis_candidate": "INTEGER DEFAULT 0",
            "original_path": "TEXT",
            "blur_score": "FLOAT",
            "brightness_score": "FLOAT",
            "contrast_score": "FLOAT",
            "face_count": "INTEGER",
            "ai_aesthetic_score": "FLOAT",
            "ai_pose_score": "FLOAT",
            "ai_expression_note": "TEXT DEFAULT ''",
            "ai_selection_reason": "TEXT DEFAULT ''",
            "ai_recommended": "INTEGER",
            "similarity_group_id": "TEXT DEFAULT ''",
            "similarity_group_size": "INTEGER DEFAULT 1",
            "best_in_group": "INTEGER DEFAULT 1",
            "is_duplicate": "INTEGER DEFAULT 0",
            "duplicate_of": "TEXT DEFAULT ''",
            "star_rating": "INTEGER DEFAULT 0",
            "color_label": "TEXT DEFAULT ''",
            "favorite": "INTEGER DEFAULT 0",
        },
    }

    with engine.begin() as connection:
        for table_name, columns in required_columns.items():
            existing_columns = {
                row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})")
            }

            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
