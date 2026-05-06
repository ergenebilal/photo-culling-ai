from pathlib import Path
import tempfile
import unittest

from src.file_manager import copy_to_category, discover_supported_files


class FileManagerPairTests(unittest.TestCase):
    def test_discovery_prefers_standard_preview_when_matching_raw_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jpg = root / "IMG_001.jpg"
            raw = root / "IMG_001.cr3"
            jpg.write_bytes(b"jpg")
            raw.write_bytes(b"raw")

            files, skipped = discover_supported_files(root)

            self.assertEqual(files, [jpg])
            self.assertEqual(skipped, 0)

    def test_copy_to_category_copies_matching_raw_sidecar_with_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            jpg = root / "IMG_001.jpg"
            raw = root / "IMG_001.cr3"
            jpg.write_bytes(b"jpg")
            raw.write_bytes(b"raw")

            copied = copy_to_category(jpg, output, "selected")

            self.assertTrue(copied.exists())
            self.assertTrue((output / "selected" / "IMG_001.cr3").exists())

    def test_discovery_skips_local_export_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "IMG_001.jpg"
            exported = root / "ErgeneAI_Output" / "Selected" / "IMG_001.jpg"
            exported.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            exported.write_bytes(b"exported")

            files, skipped = discover_supported_files(root)

            self.assertEqual(files, [source])
            self.assertEqual(skipped, 0)


if __name__ == "__main__":
    unittest.main()
