import logging
import threading
import os
import sys
import keyboard
import pyperclip
from tkinter import TclError, filedialog
import customtkinter as ctk

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

class KahootParserApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Kahoot Reincarnation Parser")
        self.geometry("950x800")
        self.configure(fg_color="#1A1A1A")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        icon_path = get_resource_path("icon.ico")
        try:
            self.iconbitmap(icon_path)
        except Exception as e:
            print(f"Icon not detecktet: {e}")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._closing = False
        self._hotkey_pending = threading.Event()
        self._poll_id = None
        self._hotkey_handle = None
        self.controller = None
        self.result_widgets = []


        self.font_title = ctk.CTkFont(family="Segoe UI", size=28, weight="bold")
        self.font_main = ctk.CTkFont(family="Segoe UI", size=15)
        self.font_bold = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        self.font_question = ctk.CTkFont(family="Segoe UI", size=17, weight="bold")


        self.header_label = ctk.CTkLabel(self, text="Kahoot Reincarnation Parser", font=self.font_title, text_color="#FFFFFF")
        self.header_label.grid(row=0, column=0, padx=20, pady=(30, 10), sticky="w")


        self.search_frame = ctk.CTkFrame(self, fg_color="#2A2D34", corner_radius=12)
        self.search_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.search_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            self.search_frame, 
            placeholder_text="Enter quiz title or paste a question...", 
            font=self.font_main,
            height=45,
            corner_radius=8,
            border_width=1,
            border_color="#3E424B",
            fg_color="#1E1F24"
        )
        self.search_entry.grid(row=0, column=0, padx=(15, 10), pady=15, sticky="ew")
        self.search_entry.bind("<Return>", lambda event: self._on_search_clicked())

        self.search_button = ctk.CTkButton(
            self.search_frame, 
            text="Search", 
            font=self.font_bold, 
            height=45,
            corner_radius=8,
            fg_color="#3B82F6", 
            hover_color="#2563EB",
            command=self._on_search_clicked
        )
        self.search_button.grid(row=0, column=1, padx=(0, 10), pady=15)

        self.export_button = ctk.CTkButton(
            self.search_frame, 
            text="Export JSON", 
            font=self.font_bold, 
            height=45,
            corner_radius=8,
            fg_color="#D97706", 
            hover_color="#B45309", 
            state="disabled", 
            command=self._on_export_clicked
        )
        self.export_button.grid(row=0, column=2, padx=(0, 15), pady=15)


        self.status_label = ctk.CTkLabel(self, text="Ready. Press F9 to search from clipboard.", font=self.font_main, text_color="#A0AEC0")
        self.status_label.grid(row=2, column=0, padx=25, pady=(0, 10), sticky="w")

        self.results_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.results_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.results_frame.grid_columnconfigure(0, weight=1)


        self._hotkey_handle = keyboard.add_hotkey('F9', self._on_hotkey_press)
        self._poll_id = self.after(50, self._poll_events)

    def set_controller(self, controller):
        self.controller = controller

    def on_closing(self):
        if self._closing:
            return
        self._closing = True
        if self.controller is not None:
            self.controller.close()
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except TclError:
                pass
            self._poll_id = None
        if self._hotkey_handle is not None:
            try:
                keyboard.remove_hotkey(self._hotkey_handle)
            except Exception:
                logging.getLogger(__name__).exception("Could not unregister F9")
            self._hotkey_handle = None
        self._hotkey_pending.clear()
        self.destroy()

    def _on_hotkey_press(self):
        if not self._closing and self.controller is not None and not self.controller.is_busy:
            self._hotkey_pending.set()

    def _poll_events(self):
        self._poll_id = None
        if self._closing:
            return
        try:
            if self.controller is not None:
                self.controller.process_pending_results()
            if self._hotkey_pending.is_set():
                self._hotkey_pending.clear()
                self._process_clipboard_search()
        finally:
            if not self._closing:
                self._poll_id = self.after(50, self._poll_events)

    def _process_clipboard_search(self):
        if self._closing or self.controller is None or self.controller.is_busy:
            return
        query = pyperclip.paste().strip()
        if not query:
            self.show_message("Clipboard is empty.", "#EF4444")
            return

        self.deiconify()
        self.attributes("-topmost", True)
        self.focus_force()
        self.attributes("-topmost", False)

        self.search_entry.delete(0, 'end')
        self.search_entry.insert(0, query)
        self._on_search_clicked()

    def _on_search_clicked(self):
        if self.controller:
            self.controller.handle_search(self.search_entry.get().strip())

    def _on_export_clicked(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save Quiz Answers"
        )
        if file_path and self.controller:
            self.controller.handle_export(file_path)

    def clear_results(self):
        for widget in self.result_widgets:
            widget.destroy()
        self.result_widgets.clear()
        self.export_button.configure(state="disabled")

    def show_loading(self, message):
        self.clear_results()
        self.status_label.configure(text=message, text_color="#FFFFFF")
        self.search_button.configure(state="disabled")
        self.search_entry.configure(state="disabled")

    def show_message(self, message, color):
        self.status_label.configure(text=message, text_color=color)
        state = "disabled" if self.controller and self.controller.is_busy else "normal"
        self.search_button.configure(state=state)
        self.search_entry.configure(state=state)

    def display_search_results(self, quizzes):
        self.search_button.configure(state="normal")
        
        if not quizzes:
            self.show_message("No public quizzes found for this query.", "#EF4444")
            return

        self.show_message(f"Found {len(quizzes)} quizzes. Select one to extract answers.", "#10B981")

        for index, quiz in enumerate(quizzes):
            btn = ctk.CTkButton(
                self.results_frame,
                text=f"{quiz['title']}   •   UUID: {quiz['uuid']}",
                font=self.font_main,
                height=50,
                corner_radius=10,
                anchor="w",
                fg_color="#2A2D34",
                hover_color="#3E424B",
                text_color="#E2E8F0",
                command=lambda u=quiz["uuid"]: self.controller.handle_fetch(u) if self.controller else None
            )
            btn.grid(row=index, column=0, padx=5, pady=5, sticky="ew")
            self.result_widgets.append(btn)

    def display_quiz_answers(self, answers_data):
        self.search_button.configure(state="normal")
        
        if not answers_data:
            self.show_message("No questions were returned for this quiz.", "#EF4444")
            return

        self.export_button.configure(state="normal")
        warning_count = sum(bool(item.get("warning")) for item in answers_data)
        unsupported_count = sum(item.get("status") == "unsupported" for item in answers_data)
        self.show_message(
            f"Loaded {len(answers_data)} items. "
            f"Unsupported: {unsupported_count}. Data warnings: {warning_count}.",
            "#D97706" if warning_count or unsupported_count else "#10B981",
        )

        for index, item in enumerate(answers_data):
            card = ctk.CTkFrame(self.results_frame, fg_color="#2A2D34", corner_radius=12)
            card.grid(row=index, column=0, padx=5, pady=10, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            self.result_widgets.append(card)

            q_label = ctk.CTkLabel(
                card,
                text=f"{index + 1}. [{item.get('type', 'unknown')}] {item['question']}",
                font=self.font_question,
                text_color="#FFFFFF",
                wraplength=800,
                justify="left"
            )
            q_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")

            details = "\n".join(filter(None, (item.get("message"), item.get("warning"))))
            if details:
                warning_label = ctk.CTkLabel(
                    card, text=details, font=self.font_main,
                    text_color="#FBBF24" if item.get("warning") else "#A0AEC0",
                    wraplength=800, justify="left",
                )
                warning_label.grid(row=1, column=0, padx=20, pady=5, sticky="w")

            has_answers = bool(item["answers"])
            answers_text = "  |  ".join(item["answers"])
            empty_text = {
                "content": "Content slide", "no_answer_required": "No correct answer required",
                "unsupported": "Unsupported format", "invalid_data": "Answers unavailable",
                "no_correct_answer": "No correct answer specified",
            }.get(item.get("status"), "Answers unavailable")
            
            a_btn = ctk.CTkButton(
                card,
                text=f"Copy Answer: {answers_text}" if has_answers else empty_text,
                state="normal" if has_answers else "disabled",
                font=self.font_bold,
                height=35,
                corner_radius=6,
                text_color="#FFFFFF",
                fg_color="#10B981",
                hover_color="#059669",
                anchor="w",
                command=lambda a=answers_text: self.controller.handle_copy(a) if self.controller else None
            )
            a_btn.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="w")