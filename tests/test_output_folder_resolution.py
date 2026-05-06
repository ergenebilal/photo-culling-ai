from pathlib import Path
import tempfile
import unittest

import app


class OutputFolderResolutionTests(unittest.TestCase):
    def test_resolves_selected_output_folder_inside_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_runs_dir = app.RUNS_DIR
            try:
                app.RUNS_DIR = Path(tmp)
                selected_dir = app.RUNS_DIR / "job-1" / "output" / "selected"
                selected_dir.mkdir(parents=True)

                resolved = app._resolve_output_folder_path("job-1", "selected")

                self.assertEqual(resolved, selected_dir.resolve())
            finally:
                app.RUNS_DIR = old_runs_dir

    def test_rejects_unknown_folder_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_runs_dir = app.RUNS_DIR
            try:
                app.RUNS_DIR = Path(tmp)

                resolved = app._resolve_output_folder_path("job-1", "secret")

                self.assertIsNone(resolved)
            finally:
                app.RUNS_DIR = old_runs_dir


if __name__ == "__main__":
    unittest.main()
