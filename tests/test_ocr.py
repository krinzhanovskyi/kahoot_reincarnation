import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.ocr import crop_selection, recognize_screen_text


class ScreenOCRTests(unittest.TestCase):
    def test_captures_all_screens_and_returns_trimmed_english_text(self):
        screenshot = SimpleNamespace(size=(1920, 1080))
        grab = Mock(return_value=screenshot)
        image_to_string = Mock(return_value="  What is 2 + 2?  \n")
        fake_pil = types.ModuleType("PIL")
        fake_pil.ImageGrab = types.SimpleNamespace(grab=grab)
        fake_tesseract = types.ModuleType("pytesseract")
        fake_tesseract.image_to_string = image_to_string

        with patch.dict(sys.modules, {"PIL": fake_pil, "pytesseract": fake_tesseract}):
            result = recognize_screen_text()

        self.assertEqual(result, "What is 2 + 2?")
        grab.assert_called_once_with()
        image_to_string.assert_called_once_with(
            screenshot, lang="eng", config="--psm 6"
        )

    def test_drag_selection_maps_preview_coordinates_to_original_pixels(self):
        image = SimpleNamespace(width=100, height=80, crop=Mock(return_value="crop"))

        result = crop_selection(
            image,
            start=(5, 10),
            end=(25, 30),
            displayed_size=(50, 40),
        )

        self.assertEqual(result, "crop")
        image.crop.assert_called_once_with((10, 20, 50, 60))

    def test_tiny_drag_selection_is_rejected(self):
        image = SimpleNamespace(width=100, height=80, crop=Mock())
        with self.assertRaisesRegex(ValueError, "too small"):
            crop_selection(
                image,
                start=(1, 1),
                end=(3, 3),
                displayed_size=(100, 80),
            )
        image.crop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
