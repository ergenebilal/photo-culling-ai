from types import SimpleNamespace
import unittest

import app


class ReportSyncTests(unittest.TestCase):
    def test_photo_to_report_record_includes_ai_and_similarity_fields(self):
        photo = SimpleNamespace(
            filename="frame.jpg",
            original_path="C:/shoot/frame.jpg",
            category="selected",
            final_score=77.5,
            blur_score=91,
            brightness_score=76,
            contrast_score=68,
            face_count=1,
            reason="Net kare.",
            similarity_group_id="group_1",
            similarity_group_size=2,
            best_in_group=1,
            is_duplicate=0,
            duplicate_of="",
            ai_analysis_candidate=1,
            ai_aesthetic_score=90,
            ai_pose_score=84,
            ai_expression_note="Eyes open.",
            ai_selection_reason="Strong delivery candidate.",
            ai_recommended=1,
            star_rating=4,
            color_label="green",
            favorite=1,
        )

        record = app._photo_to_report_record(photo)

        self.assertEqual(record["filename"], "frame.jpg")
        self.assertEqual(record["ai_aesthetic_score"], 90)
        self.assertEqual(record["ai_recommended"], 1)
        self.assertEqual(record["similarity_group_id"], "group_1")
        self.assertEqual(record["similarity_group_size"], 2)
        self.assertTrue(record["best_in_group"])
        self.assertEqual(record["blur_score"], 91)
        self.assertEqual(record["face_count"], 1)
        self.assertEqual(record["star_rating"], 4)
        self.assertEqual(record["color_label"], "green")
        self.assertTrue(record["favorite"])


if __name__ == "__main__":
    unittest.main()
