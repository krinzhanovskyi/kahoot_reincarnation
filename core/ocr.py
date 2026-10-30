"""Local screen text recognition for the F10 question-capture prototype."""

import logging

logger = logging.getLogger(__name__)


class OCRSetupError(RuntimeError):
    """Raised when the OCR Python package or Tesseract executable is missing."""


class ScreenCaptureError(RuntimeError):
    """Raised when the desktop screenshot cannot be captured or recognized."""


def capture_primary_screen():
    """Capture the primary monitor for a user-selected OCR region."""
    logger.info("Preparing screen OCR dependencies")
    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise OCRSetupError(
            "Screen capture needs Pillow. Install it with: "
            "python -m pip install Pillow"
        ) from exc

    try:
        screenshot = ImageGrab.grab()
    except Exception as exc:
        raise ScreenCaptureError(f"Could not capture the screen: {exc}") from exc
    logger.info("Captured desktop image with dimensions %s", screenshot.size)
    return screenshot


def crop_selection(image, start, end, displayed_size, minimum_size=12):
    """Map a drag rectangle from the preview to original screenshot pixels."""
    display_width, display_height = displayed_size
    if display_width <= 0 or display_height <= 0:
        raise ValueError("The screen preview has invalid dimensions.")

    scale_x = image.width / display_width
    scale_y = image.height / display_height
    left = int(min(start[0], end[0]) * scale_x)
    top = int(min(start[1], end[1]) * scale_y)
    right = int(max(start[0], end[0]) * scale_x)
    bottom = int(max(start[1], end[1]) * scale_y)
    left = max(0, min(left, image.width))
    top = max(0, min(top, image.height))
    right = max(0, min(right, image.width))
    bottom = max(0, min(bottom, image.height))

    if right - left < minimum_size or bottom - top < minimum_size:
        raise ValueError("Selection is too small. Drag around the question text.")
    return image.crop((left, top, right, bottom))


def recognize_image_text(image):
    """Return locally recognized English text from one image or crop."""
    try:
        import pytesseract
    except ImportError as exc:
        raise OCRSetupError(
            "OCR needs pytesseract. Install it with: "
            "python -m pip install pytesseract"
        ) from exc

    try:
        text = pytesseract.image_to_string(
            image,
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


def recognize_screen_text():
    """Convenience helper retained for non-GUI checks and diagnostics."""
    return recognize_image_text(capture_primary_screen())
