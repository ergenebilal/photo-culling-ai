from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import sys

import cv2
import numpy as np
import rawpy
from PIL import Image

from src.config import (
    BLUR_VARIANCE_REFERENCE,
    BLUR_WEIGHT,
    BRIGHTNESS_TARGET,
    BRIGHTNESS_WEIGHT,
    CONTRAST_REFERENCE,
    CONTRAST_WEIGHT,
    FACE_WEIGHT,
    RAW_IMAGE_EXTENSIONS,
)


@dataclass(frozen=True)
class PhotoAnalysis:
    blur_score: float
    brightness_score: float
    contrast_score: float
    face_count: int
    final_score: float
    pil_image: Image.Image


class ImageAnalyzer:
    ANALYSIS_MAX_WIDTH = 1024

    def __init__(self) -> None:
        self.face_detector = self._load_face_detector()

    def _load_face_detector(self) -> cv2.CascadeClassifier | None:
        cascade_filename = "haarcascade_frontalface_default.xml"
        candidate_paths = [
            Path(cv2.data.haarcascades) / cascade_filename,
        ]

        if hasattr(sys, "_MEIPASS"):
            candidate_paths.append(Path(sys._MEIPASS) / "cv2" / "data" / cascade_filename)

        for cascade_path in candidate_paths:
            detector = cv2.CascadeClassifier(str(cascade_path))
            if not detector.empty():
                return detector

        # Yüz modeli bulunamazsa analiz devam eder; yalnızca yüz bonusu uygulanmaz.
        return None

    def analyze(self, image_path: Path, thumbnail_path: Path | None = None) -> PhotoAnalysis:
        rgb_image = self._load_rgb_image(image_path)
        rgb_image = self._resize_for_analysis(rgb_image)
        gray_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)

        blur_score = self._calculate_blur_score(gray_image)
        brightness_score = self._calculate_brightness_score(gray_image)
        contrast_score = self._calculate_contrast_score(gray_image)
        face_count = self._detect_faces(gray_image)
        final_score = self._calculate_final_score(
            blur_score=blur_score,
            brightness_score=brightness_score,
            contrast_score=contrast_score,
            face_count=face_count,
        )

        pil_image = Image.fromarray(rgb_image)
        pil_image.thumbnail((800, 800))

        if thumbnail_path:
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            pil_image.save(thumbnail_path, "JPEG", quality=80)

        return PhotoAnalysis(
            blur_score=blur_score,
            brightness_score=brightness_score,
            contrast_score=contrast_score,
            face_count=face_count,
            final_score=final_score,
            pil_image=pil_image.copy(),
        )

    def _load_rgb_image(self, image_path: Path) -> np.ndarray:
        suffix = image_path.suffix.lower()

        if suffix in RAW_IMAGE_EXTENSIONS:
            return self._load_raw_preview(image_path)

        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Görsel dosyası okunamadı.")

        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    def _load_raw_preview(self, image_path: Path) -> np.ndarray:
        with rawpy.imread(str(image_path)) as raw:
            try:
                thumbnail = raw.extract_thumb()
                if thumbnail.format == rawpy.ThumbFormat.JPEG:
                    image = Image.open(BytesIO(thumbnail.data)).convert("RGB")
                    return np.array(image)
                if thumbnail.format == rawpy.ThumbFormat.BITMAP:
                    return np.asarray(thumbnail.data, dtype=np.uint8)
            except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                pass

            # RAW içinde önizleme yoksa analiz akışı bozulmasın diye tam çözümleme yapılır.
            return raw.postprocess(use_camera_wb=True, no_auto_bright=True)

    def _resize_for_analysis(self, rgb_image: np.ndarray) -> np.ndarray:
        height, width = rgb_image.shape[:2]
        if width <= self.ANALYSIS_MAX_WIDTH:
            return rgb_image

        scale = self.ANALYSIS_MAX_WIDTH / width
        target_height = max(1, int(height * scale))
        return cv2.resize(
            rgb_image,
            (self.ANALYSIS_MAX_WIDTH, target_height),
            interpolation=cv2.INTER_AREA,
        )

    def _calculate_blur_score(self, gray_image: np.ndarray) -> float:
        variance = cv2.Laplacian(gray_image, cv2.CV_64F).var()
        score = (variance / BLUR_VARIANCE_REFERENCE) * 100.0
        return round(float(np.clip(score, 0.0, 100.0)), 2)

    def _calculate_brightness_score(self, gray_image: np.ndarray) -> float:
        mean_brightness = float(np.mean(gray_image))
        distance = abs(mean_brightness - BRIGHTNESS_TARGET)
        score = 100.0 - ((distance / BRIGHTNESS_TARGET) * 100.0)
        return round(float(np.clip(score, 0.0, 100.0)), 2)

    def _calculate_contrast_score(self, gray_image: np.ndarray) -> float:
        contrast = float(np.std(gray_image))
        score = (contrast / CONTRAST_REFERENCE) * 100.0
        return round(float(np.clip(score, 0.0, 100.0)), 2)

    def _detect_faces(self, gray_image: np.ndarray) -> int:
        if self.face_detector is None:
            return 0

        faces = self.face_detector.detectMultiScale(
            gray_image,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
        )
        return int(len(faces))

    def _calculate_final_score(
        self,
        blur_score: float,
        brightness_score: float,
        contrast_score: float,
        face_count: int,
    ) -> float:
        face_score = 100.0 if face_count > 0 else 0.0
        final_score = (
            blur_score * BLUR_WEIGHT
            + brightness_score * BRIGHTNESS_WEIGHT
            + contrast_score * CONTRAST_WEIGHT
            + face_score * FACE_WEIGHT
        )
        return round(float(np.clip(final_score, 0.0, 100.0)), 2)
