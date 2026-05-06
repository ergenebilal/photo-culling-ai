from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ai_scorer import AIPhotoScorer
from src.ai_settings import load_ai_settings, public_ai_settings, save_ai_settings


class AISettingsTests(unittest.TestCase):
    def test_save_load_and_mask_api_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "ai_settings.json"
            with patch.dict(os.environ, {"ERGENEAI_AI_SETTINGS_PATH": str(settings_path)}, clear=False):
                settings = save_ai_settings(
                    api_key="sk-test-123456",
                    model="gpt-test",
                    base_url="https://example.test/v1",
                    enabled=True,
                )

                self.assertTrue(settings_path.exists())
                self.assertEqual(load_ai_settings().api_key, "sk-test-123456")
                self.assertEqual(load_ai_settings().model, "gpt-test")

                public_payload = public_ai_settings(settings)
                self.assertTrue(public_payload["has_api_key"])
                self.assertEqual(public_payload["api_key_mask"], "sk-...3456")
                self.assertNotIn("api_key", public_payload)

    def test_ai_scorer_reads_saved_settings_without_env_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "ai_settings.json"
            env = {
                "ERGENEAI_AI_SETTINGS_PATH": str(settings_path),
                "OPENAI_API_KEY": "",
                "OPENAI_MODEL": "",
                "OPENAI_BASE_URL": "",
                "AI_ENABLED": "",
            }
            with patch.dict(os.environ, env, clear=False):
                os.environ.pop("OPENAI_API_KEY", None)
                os.environ.pop("OPENAI_MODEL", None)
                os.environ.pop("OPENAI_BASE_URL", None)
                os.environ.pop("AI_ENABLED", None)
                save_ai_settings(api_key="sk-local-key", model="gpt-local", enabled=True)

                scorer = AIPhotoScorer.from_env()

                self.assertTrue(scorer.enabled)
                self.assertEqual(scorer.api_key, "sk-local-key")
                self.assertEqual(scorer.model, "gpt-local")

    def test_clear_api_key_keeps_other_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "ai_settings.json"
            with patch.dict(os.environ, {"ERGENEAI_AI_SETTINGS_PATH": str(settings_path)}, clear=False):
                save_ai_settings(api_key="sk-test-123456", model="gpt-test", enabled=False)
                settings = save_ai_settings(clear_api_key=True)

                self.assertFalse(settings.has_api_key)
                self.assertEqual(settings.model, "gpt-test")
                self.assertFalse(settings.enabled)


if __name__ == "__main__":
    unittest.main()
