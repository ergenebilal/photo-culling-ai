from __future__ import annotations

from src.analyzer import PhotoAnalysis
from src.config import (
    CATEGORY_REJECTED,
    CATEGORY_SELECTED,
    SELECTED_THRESHOLD,
)


def classify_photo(analysis: PhotoAnalysis) -> tuple[str, str]:
    if analysis.final_score >= SELECTED_THRESHOLD:
        return CATEGORY_SELECTED, _build_selected_reason(analysis)

    return CATEGORY_REJECTED, _build_rejected_reason(analysis)


def _build_selected_reason(analysis: PhotoAnalysis) -> str:
    details: list[str] = []

    if analysis.blur_score >= 70:
        details.append("net")
    if analysis.brightness_score >= 70:
        details.append("ışık dengeli")
    if analysis.contrast_score >= 65:
        details.append("kontrastı güçlü")
    if analysis.face_count > 0:
        details.append("yüz tespit edildi")

    if details:
        return f"Fotoğraf {_join_turkish(details)}; bu nedenle selected kategorisine alındı."

    return "Fotoğraf genel kalite skoru yüksek olduğu için selected kategorisine alındı."


def _build_rejected_reason(analysis: PhotoAnalysis) -> str:
    weak_points = _find_weak_points(analysis)

    if analysis.blur_score < 45:
        return "Fotoğraf bulanık olduğu için elenenler arasına alındı."

    if weak_points:
        return (
            f"Fotoğraf {', '.join(weak_points)} nedeniyle elenenler arasına alındı."
        )

    return "Fotoğraf final kalite skoru seçilenler eşiğinin altında kaldığı için elenenler arasına alındı."


def _find_weak_points(analysis: PhotoAnalysis) -> list[str]:
    weak_points: list[str] = []

    if analysis.blur_score < 55:
        weak_points.append("netlik düşük")
    if analysis.brightness_score < 55:
        weak_points.append("ışık dengesi zayıf")
    if analysis.contrast_score < 45:
        weak_points.append("kontrast düşük")
    if analysis.face_count == 0:
        weak_points.append("yüz tespit edilmedi")

    return weak_points


def _join_turkish(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} ve {parts[-1]}"
