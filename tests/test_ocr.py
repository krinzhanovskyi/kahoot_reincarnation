import sys
import types
import unittest
from unittest.mock import Mock, patch

from core.ocr import recognize_screen_text


class ScreenOCRTests(unittest.TestCase):
    def test_captures_all_screens_and_returns_trimmed_english_text(self):
        screenshot = object()
        grab = Mock(return_value=screenshot)
        image_to_string = Mock(return_value="  What is 2 + 2?  \n")
        fake_pil = types.ModuleType("PIL")
        fake_pil.ImageGrab = types.SimpleNamespace(grab=grab)
        fake_tesseract = types.ModuleType("pytesseract")
        fake_tesseract.image_to_string = image_to_string

        with patch.dict(sys.modules, {"PIL": fake_pil, "pytesseract": fake_tesseract}):
            result = recognize_screen_text()

        self.assertEqual(result, "What is 2 + 2?")
        grab.assert_called_once_with(all_screens=True)
        image_to_string.assert_called_once_with(
            screenshot, lang="eng", config="--psm 6"
        )


if __name__ == "__main__":
    unittest.main()
