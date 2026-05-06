from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import app


class PhotoAssetResolutionTests(unittest.TestCase):
    def test_prefers_thumbnail_for_thumb_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_runs_dir = app.RUNS_DIR
            try:
                app.RUNS_DIR = Path(tmp)
                job_id = "job-1"
                thumb = app.RUNS_DIR / job_id / "thumbnails" / "frame.jpg"
                full = app.RUNS_DIR / job_id / "output" / "selected" / "frame.jpg"
                thumb.parent.mkdir(parents=True)
                full.parent.mkdir(parents=True)
                thumb.write_bytes(b"thumb")
                full.write_bytes(b"full")
                photo = SimpleNamespace(
                    thumbnail_path="thumbnails/frame.jpg",
                    relative_path="output/selected/frame.jpg",
                    original_path=str(full),
                )

                resolved = app._resolve_photo_asset_path(job_id, photo, "thumb")

                self.assertEqual(resolved, thumb)
            finally:
                app.RUNS_DIR = old_runs_dir

    def test_full_variant_rejects_missing_runs_copy_instead_of_original_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_runs_dir = app.RUNS_DIR
            try:
                app.RUNS_DIR = Path(tmp) / "runs"
                outside = Path(tmp) / "outside.jpg"
                outside.write_bytes(b"outside")
                photo = SimpleNamespace(
                    thumbnail_path="",
                    relative_path="output/rejected/outside.jpg",
                    original_path=str(outside),
                )

                resolved = app._resolve_photo_asset_path("job-1", photo, "full")

                self.assertIsNone(resolved)
            finally:
                app.RUNS_DIR = old_runs_dir


if __name__ == "__main__":
    unittest.main()
