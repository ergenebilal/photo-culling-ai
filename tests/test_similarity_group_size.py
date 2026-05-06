import unittest

from PIL import Image

from src.similarity import mark_similar_groups


def make_record(filename: str, score: float, color: tuple[int, int, int]) -> dict:
    return {
        "filename": filename,
        "final_score": score,
        "image_for_hash": Image.new("RGB", (32, 32), color),
    }


class SimilarityGroupSizeTests(unittest.TestCase):
    def test_single_photo_group_has_size_one_without_duplicate(self):
        records = [make_record("single.jpg", 70, (20, 40, 60))]

        result = mark_similar_groups(records)

        self.assertEqual(result[0]["similarity_group_size"], 1)
        self.assertTrue(result[0]["best_in_group"])
        self.assertFalse(result[0]["is_duplicate"])

    def test_multi_photo_group_marks_only_highest_score_as_best(self):
        records = [
            make_record("lower.jpg", 60, (80, 80, 80)),
            make_record("higher.jpg", 90, (80, 80, 80)),
        ]

        result = mark_similar_groups(records)

        self.assertEqual(result[0]["similarity_group_size"], 2)
        self.assertEqual(result[1]["similarity_group_size"], 2)
        self.assertFalse(result[0]["best_in_group"])
        self.assertTrue(result[1]["best_in_group"])
        self.assertTrue(result[0]["is_duplicate"])
        self.assertEqual(result[0]["duplicate_of"], "higher.jpg")


if __name__ == "__main__":
    unittest.main()
