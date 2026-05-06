from pathlib import Path
import unittest


TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "result.html"


class ResultTemplateTests(unittest.TestCase):
    def test_result_template_contains_lightbox_and_filename_controls(self):
        html = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn('id="photo-lightbox"', html)
        self.assertIn('data-photo-id="{{ photo.id }}"', html)
        self.assertIn('data-full-src="/photo/{{ job_id }}/{{ photo.id }}/image?variant=full"', html)
        self.assertIn("openLightbox", html)
        self.assertIn("handleLightboxKeydown", html)
        self.assertIn("openOutputFolder('{{ job_id }}', 'selected')", html)
        self.assertIn("ZIP İndir", html)
        self.assertIn('data-group="{{ photo.similarity_group_id or \'Tekil\' }}"', html)
        self.assertIn("Benzer Grup", html)
        self.assertIn("runAIAnalysis('{{ job_id }}')", html)
        self.assertIn('data-ai-aesthetic="{{ photo.ai_aesthetic_score if photo.ai_aesthetic_score is not none else \'--\' }}"', html)
        self.assertIn("AI Gerekçesi", html)
        self.assertIn('data-best-in-group="{{ 1 if photo.best_in_group else 0 }}"', html)
        self.assertIn('data-group-size="{{ photo.similarity_group_size or 1 }}"', html)
        self.assertIn("{% if photo.best_in_group and (photo.similarity_group_size or 1) > 1 %}", html)
        self.assertIn("Grubun En İyisi", html)
        self.assertIn('data-rating="{{ photo.star_rating or 0 }}"', html)
        self.assertIn('data-favorite="{{ 1 if photo.favorite else 0 }}"', html)
        self.assertIn('data-label="{{ photo.color_label or \'\' }}"', html)
        self.assertIn("Profesyonel Ayıklama", html)
        self.assertIn("updatePhotoMetadata", html)
        self.assertIn("applyGalleryFilter", html)
        self.assertIn('id="compare-stack-modal"', html)
        self.assertIn("Side-by-side Compare", html)
        self.assertIn("openCompareStackFromCard", html)
        self.assertIn("openCurrentCompareStack", html)
        self.assertIn("renderCompareStack", html)
        self.assertIn("getStackCards", html)
        self.assertIn("data-compare-grid", html)


if __name__ == "__main__":
    unittest.main()
