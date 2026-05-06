from types import SimpleNamespace
import unittest

import app
from src.ai_scorer import AIPhotoScore


class AIApplicationTests(unittest.TestCase):
    def test_apply_ai_score_updates_photo_fields(self):
        photo = SimpleNamespace(
            ai_aesthetic_score=None,
            ai_pose_score=None,
            ai_expression_note="",
            ai_selection_reason="",
            ai_recommended=None,
        )
        score = AIPhotoScore(
            ai_aesthetic_score=88.5,
            ai_pose_score=91,
            ai_expression_note="Eyes open.",
            ai_selection_reason="Strong client delivery candidate.",
            ai_recommended=True,
        )

        app._apply_ai_score_to_photo(photo, score)

        self.assertEqual(photo.ai_aesthetic_score, 88.5)
        self.assertEqual(photo.ai_pose_score, 91)
        self.assertEqual(photo.ai_expression_note, "Eyes open.")
        self.assertEqual(photo.ai_selection_reason, "Strong client delivery candidate.")
        self.assertEqual(photo.ai_recommended, 1)


if __name__ == "__main__":
    unittest.main()
