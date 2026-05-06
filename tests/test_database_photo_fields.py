import unittest

from src.database import PhotoResult


class DatabasePhotoFieldsTests(unittest.TestCase):
    def test_photo_result_exposes_similarity_fields(self):
        photo = PhotoResult()

        self.assertTrue(hasattr(photo, "similarity_group_id"))
        self.assertTrue(hasattr(photo, "best_in_group"))
        self.assertTrue(hasattr(photo, "is_duplicate"))
        self.assertTrue(hasattr(photo, "duplicate_of"))
        self.assertTrue(hasattr(photo, "similarity_group_size"))
        self.assertTrue(hasattr(photo, "blur_score"))
        self.assertTrue(hasattr(photo, "brightness_score"))
        self.assertTrue(hasattr(photo, "contrast_score"))
        self.assertTrue(hasattr(photo, "face_count"))
        self.assertTrue(hasattr(photo, "star_rating"))
        self.assertTrue(hasattr(photo, "color_label"))
        self.assertTrue(hasattr(photo, "favorite"))


if __name__ == "__main__":
    unittest.main()
