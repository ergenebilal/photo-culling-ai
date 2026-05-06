from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_AI_MODEL = "gpt-4.1-mini"


@dataclass(frozen=True)
class AISettings:
    api_key: str = ""
    model: str = DEFAULT_AI_MODEL
    base_url: str = ""
    enabled: bool = True

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.strip())


def get_ai_settings_path() -> Path:
    override_path = os.getenv("ERGENEAI_AI_SETTINGS_PATH", "").strip()
    if override_path:
        return Path(override_path)

    fallback_root = os.getenv("USERPROFILE", "") or str(Path.cwd())
    app_data_root = Path(os.getenv("LOCALAPPDATA", fallback_root)) / "ErgeneAI"
    return app_data_root / "config" / "ai_settings.json"


def load_ai_settings() -> AISettings:
    settings_path = get_ai_settings_path()
    if not settings_path.exists():
        return AISettings()

    try:
        with settings_path.open("r", encoding="utf-8") as settings_file:
            payload = json.load(settings_file)
    except Exception:
        return AISettings()

    if not isinstance(payload, dict):
        return AISettings()

    return AISettings(
        api_key=str(payload.get("api_key") or "").strip(),
        model=_normalize_model(payload.get("model")),
        base_url=str(payload.get("base_url") or "").strip(),
        enabled=bool(payload.get("enabled", True)),
    )


def save_ai_settings(
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    enabled: bool | None = None,
    clear_api_key: bool = False,
) -> AISettings:
    current = load_ai_settings()
    next_settings = AISettings(
        api_key="" if clear_api_key else (current.api_key if api_key is None else api_key.strip()),
        model=_normalize_model(model if model is not None else current.model),
        base_url=current.base_url if base_url is None else base_url.strip(),
        enabled=current.enabled if enabled is None else bool(enabled),
    )

    settings_path = get_ai_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with settings_path.open("w", encoding="utf-8") as settings_file:
        json.dump(asdict(next_settings), settings_file, ensure_ascii=False, indent=2)

    return next_settings


def get_effective_ai_settings() -> AISettings:
    settings = load_ai_settings()

    enabled_value = os.getenv("AI_ENABLED")
    enabled = settings.enabled
    if enabled_value is not None:
        enabled = enabled_value.strip().lower() not in {"0", "false", "no", "off"}

    return AISettings(
        api_key=os.getenv("OPENAI_API_KEY", settings.api_key).strip(),
        model=_normalize_model(os.getenv("OPENAI_MODEL", settings.model)),
        base_url=os.getenv("OPENAI_BASE_URL", settings.base_url).strip(),
        enabled=enabled,
    )


def public_ai_settings(settings: AISettings | None = None) -> dict[str, Any]:
    settings = settings or load_ai_settings()
    return {
        "enabled": settings.enabled,
        "has_api_key": settings.has_api_key,
        "api_key_mask": mask_api_key(settings.api_key),
        "model": settings.model,
        "base_url": settings.base_url,
    }


def mask_api_key(api_key: str) -> str:
    stripped = api_key.strip()
    if not stripped:
        return ""
    if len(stripped) <= 8:
        return "********"
    return f"{stripped[:3]}...{stripped[-4:]}"


def _normalize_model(value: Any) -> str:
    model = str(value or "").strip()
    return model or DEFAULT_AI_MODEL
