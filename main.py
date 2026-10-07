import customtkinter as ctk
from gui.app import KahootParserApp

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = KahootParserApp()
    app.mainloop()