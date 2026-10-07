import sys
import customtkinter as ctk
from gui.app import KahootParserApp

def quiet_interrupt_handler(exctype, value, traceback):
    if exctype == KeyboardInterrupt:
        sys.exit(0)
    else:
        sys.__excepthook__(exctype, value, traceback)

sys.excepthook = quiet_interrupt_handler

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = KahootParserApp()
    
    try:
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)