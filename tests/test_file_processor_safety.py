import shutil
import tempfile
import unittest
from pathlib import Path

from actions import file_processor


class FileProcessorSafetyTests(unittest.TestCase):
    def setUp(self):
        # Inside the user's home, so the location guard is not what refuses it.
        self.root = Path(tempfile.mkdtemp(dir=Path.home()))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_credential_store_is_refused_before_it_is_read(self):
        secret = self.root / "api_keys.json"
        secret.write_text('{"key": "not-a-real-secret"}', encoding="utf-8")

        result = file_processor.file_processor({"file_path": str(secret)})

        self.assertIn("credentials", result)
        self.assertNotIn("not-a-real-secret", result)


if __name__ == "__main__":
    unittest.main()
