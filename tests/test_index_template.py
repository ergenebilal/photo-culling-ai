from pathlib import Path
import unittest


TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "index.html"


class IndexTemplateTests(unittest.TestCase):
    def test_index_template_contains_ai_settings_module(self):
        html = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("AI API Ayarları", html)
        self.assertIn('id="ai-api-key-input"', html)
        self.assertIn('id="ai-model-input"', html)
        self.assertIn("saveAISettings", html)
        self.assertIn("fetch('/settings/ai'", html)


if __name__ == "__main__":
    unittest.main()
