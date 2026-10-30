class OCRSetupError(RuntimeError):
    """OCR dependencies or the Tesseract executable are unavailable."""


class ScreenCaptureError(RuntimeError):
    """The screen could not be captured or recognized."""


def recognize_screen_text():
    try:
        from PIL import ImageGrab
        import pytesseract
    except ImportError as exc:
        raise OCRSetupError(
            "OCR needs Pillow and pytesseract. Install them with: "
            "python -m pip install Pillow pytesseract"
        ) from exc

    try:
        screenshot = ImageGrab.grab(all_screens=True)
    except Exception as exc:
        raise ScreenCaptureError(f"Could not capture the screen: {exc}") from exc

    try:
        return pytesseract.image_to_string(
            screenshot,
            lang="eng",
            config="--psm 6",
        ).strip()
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise OCRSetupError(
            "Tesseract OCR is not installed or is missing from PATH. "
            "Install Tesseract OCR, then restart the app."
        ) from exc
    except Exception as exc:
        raise ScreenCaptureError(f"Could not recognize screen text: {exc}") from exc
