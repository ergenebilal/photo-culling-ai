from types import SimpleNamespace
import unittest

import app


class PhotoMetadataTests(unittest.TestCase):
    def test_apply_photo_metadata_update_clamps_and_normalizes_values(self):
        photo = SimpleNamespace(star_rating=0, color_label="", favorite=0)

        app._apply_photo_metadata_update(
            photo,
            app.PhotoMetadataRequest(star_rating=8, color_label=" GREEN ", favorite=True),
        )

        self.assertEqual(photo.star_rating, 5)
        self.assertEqual(photo.color_label, "green")
        self.assertEqual(photo.favorite, 1)

    def test_apply_photo_metadata_update_rejects_unknown_color_label(self):
        photo = SimpleNamespace(star_rating=3, color_label="red", favorite=1)

        app._apply_photo_metadata_update(
            photo,
            app.PhotoMetadataRequest(star_rating=2, color_label="purple", favorite=False),
        )

        self.assertEqual(photo.star_rating, 2)
        self.assertEqual(photo.color_label, "")
        self.assertEqual(photo.favorite, 0)


if __name__ == "__main__":
    unittest.main()
