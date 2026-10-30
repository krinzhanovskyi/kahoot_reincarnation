import logging
import os
import sys
import ctypes
import customtkinter as ctk
from gui.app import KahootParserApp
from core.controller import KahootController


def set_windows_app_id():
    """Give this process its own Windows taskbar identity."""
    if sys.platform != "win32":
        return

    try:
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Krizhanovskyi.KahootReincarnation"
        )
    except (AttributeError, OSError) as exc:
        logging.getLogger(__name__).warning(
            "Could not set Windows application ID: %s", exc
        )
        return

    if result != 0:
        logging.getLogger(__name__).warning(
            "Windows rejected the application ID (HRESULT %s)", result
        )

def quiet_interrupt_handler(exctype, value, traceback):
    if isinstance(exctype, type) and issubclass(exctype, KeyboardInterrupt):
        sys.exit(0)
    else:
        logging.getLogger(__name__).critical(
            "Uncaught exception", exc_info=(exctype, value, traceback)
        )
        sys.__excepthook__(exctype, value, traceback)

sys.excepthook = quiet_interrupt_handler

if __name__ == "__main__":
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kahoot_parser.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logging.getLogger(__name__).info("Starting Kahoot Reincarnation Parser")
    ctk.set_appearance_mode("Dark")
    set_windows_app_id()
    
    app = KahootParserApp()
    controller = KahootController(app)
    app.set_controller(controller)
    
    try:
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
