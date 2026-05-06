from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
from typing import Any

from PIL import Image

from src.ai_settings import DEFAULT_AI_MODEL, get_effective_ai_settings

DEFAULT_AI_MAX_IMAGE_SIZE = 1024


@dataclass(frozen=True)
class AIPhotoScore:
    ai_aesthetic_score: float | None = None
    ai_pose_score: float | None = None
    ai_expression_note: str = ""
    ai_selection_reason: str = ""
    ai_recommended: bool | None = None


class AIPhotoScorer:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_AI_MODEL,
        base_url: str | None = None,
        enabled: bool = True,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.model = model
        self.base_url = (base_url or "").strip() or None
        self.enabled = enabled and bool(self.api_key)

    @classmethod
    def from_env(cls) -> "AIPhotoScorer":
        settings = get_effective_ai_settings()
        return cls(
            api_key=settings.api_key,
            model=settings.model,
            base_url=settings.base_url,
            enabled=settings.enabled,
        )

    def score_photo(self, image_path: Path) -> AIPhotoScore:
        if not self.enabled:
            return AIPhotoScore()

        try:
            from openai import OpenAI
        except ImportError:
            return AIPhotoScore(
                ai_expression_note="OpenAI paketi kurulu olmadığı için AI analiz atlandı.",
                ai_selection_reason="Yerel teknik skor kullanıldı.",
            )

        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _build_ai_prompt()},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _image_to_data_url(image_path),
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=500,
        )
        content = response.choices[0].message.content or ""
        return parse_ai_score_payload(content)


def parse_ai_score_payload(payload: str) -> AIPhotoScore:
    try:
        data = json.loads(_extract_json_object(payload))
    except Exception:
        return AIPhotoScore()

    return AIPhotoScore(
        ai_aesthetic_score=_clamp_score(data.get("aesthetic_score")),
        ai_pose_score=_clamp_score(data.get("pose_score")),
        ai_expression_note=str(data.get("expression_note") or "")[:500],
        ai_selection_reason=str(data.get("selection_reason") or "")[:500],
        ai_recommended=_coerce_optional_bool(data.get("recommended")),
    )


def _extract_json_object(payload: str) -> str:
    text = payload.strip()
    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _clamp_score(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, round(number, 2)))


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "recommended"}:
            return True
        if lowered in {"false", "no", "0", "rejected"}:
            return False
    return None


def _build_ai_prompt() -> str:
    return (
        "You are a professional photo culling assistant. Evaluate this single photo for delivery selection. "
        "Return only valid JSON with these keys: aesthetic_score, pose_score, expression_note, "
        "selection_reason, recommended. Scores must be 0-100. recommended must be true or false. "
        "Focus on sharpness, lighting, composition, subject expression, eyes, motion blur, and overall client delivery value."
    )


def _image_to_data_url(image_path: Path) -> str:
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((DEFAULT_AI_MAX_IMAGE_SIZE, DEFAULT_AI_MAX_IMAGE_SIZE))
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=85)

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
