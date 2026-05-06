from pathlib import Path
import tempfile
import unittest

import app


class LocalExportTests(unittest.TestCase):
    def test_builds_local_export_folder_next_to_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "shoot"
            source.mkdir()

            export_dir = app._build_local_export_dir(source)

            self.assertEqual(export_dir, source / "ErgeneAI_Output")

    def test_mirrors_selected_rejected_and_reports_to_local_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_output = root / "run" / "output"
            export = root / "shoot" / "ErgeneAI_Output"
            (run_output / "selected").mkdir(parents=True)
            (run_output / "rejected").mkdir(parents=True)
            (run_output / "selected" / "good.jpg").write_bytes(b"good")
            (run_output / "rejected" / "bad.jpg").write_bytes(b"bad")
            (run_output / "report.csv").write_text("filename\n", encoding="utf-8")
            (run_output / "report.json").write_text("[]", encoding="utf-8")

            app._mirror_output_to_local_export(run_output, export)

            self.assertTrue((export / "Selected" / "good.jpg").exists())
            self.assertTrue((export / "Rejected" / "bad.jpg").exists())
            self.assertTrue((export / "report.csv").exists())
            self.assertTrue((export / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
