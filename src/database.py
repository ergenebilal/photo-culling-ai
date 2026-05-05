from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True)
    status = Column(String, default="processing")
    message = Column(Text)
    total_count = Column(Integer, default=0)
    selected_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PhotoResult(Base):
    __tablename__ = "photo_results"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, index=True)
    filename = Column(String)
    category = Column(String)
    final_score = Column(Float)
    reason = Column(Text)
    relative_path = Column(String)  # Path relative to runs/{job_id}/output/
    thumbnail_path = Column(String) # Path relative to runs/{job_id}/


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
