import json
import os
from unittest import mock
import unittest

from src.ai_scorer import AIPhotoScore, AIPhotoScorer, parse_ai_score_payload


class AIScorerTests(unittest.TestCase):
    def test_disabled_without_api_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            scorer = AIPhotoScorer.from_env()

        self.assertFalse(scorer.enabled)

    def test_parse_ai_score_payload_clamps_and_normalizes_values(self):
        payload = json.dumps(
            {
                "aesthetic_score": 140,
                "pose_score": -5,
                "expression_note": "Eyes open, expression usable.",
                "selection_reason": "Strongest frame in the set.",
                "recommended": True,
            }
        )

        score = parse_ai_score_payload(payload)

        self.assertEqual(score.ai_aesthetic_score, 100)
        self.assertEqual(score.ai_pose_score, 0)
        self.assertEqual(score.ai_expression_note, "Eyes open, expression usable.")
        self.assertTrue(score.ai_recommended)

    def test_parse_ai_score_payload_handles_invalid_json(self):
        score = parse_ai_score_payload("not json")

        self.assertEqual(score, AIPhotoScore())


if __name__ == "__main__":
    unittest.main()
