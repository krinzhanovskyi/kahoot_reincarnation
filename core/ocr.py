"""Local screen text recognition for the F10 question-capture prototype."""

import logging

logger = logging.getLogger(__name__)


class OCRSetupError(RuntimeError):
    """Raised when the OCR Python package or Tesseract executable is missing."""


class ScreenCaptureError(RuntimeError):
    """Raised when the desktop screenshot cannot be captured or recognized."""


def recognize_screen_text():
    """Capture the desktop and return locally recognized English text."""
    logger.info("Preparing screen OCR dependencies")
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
    logger.info("Captured desktop image with dimensions %s", screenshot.size)

    try:
        text = pytesseract.image_to_string(
            screenshot,
            lang="eng",
            config="--psm 6",
        ).strip()
        logger.info("Tesseract OCR returned %d characters", len(text))
        return text
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise OCRSetupError(
            "Tesseract OCR is not installed or is missing from PATH. "
            "Install Tesseract OCR, then restart the app."
        ) from exc
    except Exception as exc:
        raise ScreenCaptureError(f"Could not recognize screen text: {exc}") from exc
