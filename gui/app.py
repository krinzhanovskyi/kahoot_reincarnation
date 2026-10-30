import logging
import queue
import threading
import os
import sys
import keyboard
import pyperclip
from tkinter import Misc, TclError, filedialog
import customtkinter as ctk
from core.ocr import recognize_screen_text

logger = logging.getLogger(__name__)

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
        self.minsize(600, 400)
        self.configure(fg_color="#1A1A1A")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        icon_path = get_resource_path("icon.ico")
        try:
            self.iconbitmap(default=icon_path)
        except TclError as exc:
            logger.warning("Could not load window icon %s: %s", icon_path, exc)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._closing = False
        self._hotkey_pending = threading.Event()
        self._capture_pending = threading.Event()
        self._ocr_results = queue.Queue()
        self._ocr_in_progress = False
        self._poll_id = None
        self._hotkey_handle = None
        self._capture_hotkey_handle = None
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


        self.status_label = ctk.CTkLabel(self, text="F9: search clipboard. F10: recognize visible screen text.", font=self.font_main, text_color="#A0AEC0")
        self.status_label.grid(row=2, column=0, padx=25, pady=(0, 10), sticky="w")

        self.results_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.results_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.results_frame.grid_columnconfigure(0, weight=1)


        self._register_hotkey()
        self._poll_id = self.after(50, self._poll_events)

    def _register_hotkey(self):
        try:
            self._hotkey_handle = keyboard.add_hotkey('F9', self._on_hotkey_press)
            logger.info("Registered F9 clipboard-search hotkey")
        except Exception:
            logger.exception("Could not register F9")
            self._hotkey_handle = None
            self.show_message("F9 is unavailable. Enter a query and use Search instead.", "#D97706")

        try:
            self._capture_hotkey_handle = keyboard.add_hotkey(
                'F10', self._on_capture_hotkey_press
            )
            logger.info("Registered F10 screen-OCR hotkey")
        except Exception:
            logger.exception("Could not register F10")
            self._capture_hotkey_handle = None
            self.show_message(
                "F10 OCR is unavailable. Enter the question manually.",
                "#D97706",
            )

    def set_controller(self, controller):
        self.controller = controller
        logger.info("Controller attached to GUI")

    def report_callback_exception(self, exc, value, traceback):
        logger.error(
            "Unhandled exception in GUI callback",
            exc_info=(exc, value, traceback),
        )

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
        for handle, name in (
            (self._hotkey_handle, "F9"),
            (self._capture_hotkey_handle, "F10"),
        ):
            if handle is not None:
                try:
                    keyboard.remove_hotkey(handle)
                except Exception:
                    logger.exception("Could not unregister %s", name)
        self._hotkey_handle = None
        self._capture_hotkey_handle = None
        self._hotkey_pending.clear()
        self._capture_pending.clear()
        self.destroy()

    def _on_hotkey_press(self):
        if not self._closing and self.controller is not None and not self.controller.is_busy:
            logger.info("F9 hotkey received")
            self._hotkey_pending.set()
        else:
            logger.info("Ignored F9 hotkey: app closing, controller missing, or request busy")

    def _poll_events(self):
        self._poll_id = None
        if self._closing:
            return
        try:
            if self.controller is not None:
                self.controller.process_pending_results()
            if self._capture_pending.is_set():
                self._capture_pending.clear()
                logger.info("F10 event reached GUI event loop")
                self._start_screen_ocr()
            self._apply_ocr_result()
            if self._hotkey_pending.is_set():
                self._hotkey_pending.clear()
                self._process_clipboard_search()
        finally:
            if not self._closing:
                self._poll_id = self.after(50, self._poll_events)

    def _on_capture_hotkey_press(self):
        if (
            not self._closing
            and self.controller is not None
            and not self.controller.is_busy
            and not self._ocr_in_progress
        ):
            logger.info("F10 hotkey received")
            self._capture_pending.set()
        else:
            logger.info("Ignored F10 hotkey: app closing, controller missing, request busy, or OCR active")

    def _start_screen_ocr(self):
        """Run screen OCR off the GUI thread after F10 is pressed."""
        if (
            self._closing
            or self.controller is None
            or self.controller.is_busy
            or self._ocr_in_progress
        ):
            logger.info("Skipped OCR start: app closing, controller missing, request busy, or OCR active")
            return
        self._ocr_in_progress = True
        logger.info("Starting screen OCR worker")
        self.show_message("Reading visible screen text…", "#A0AEC0")
        try:
            threading.Thread(target=self._screen_ocr_worker, daemon=True).start()
        except RuntimeError:
            self._ocr_in_progress = False
            logger.exception("Could not start screen OCR worker")
            self.show_message("Could not start OCR. See kahoot_parser.log.", "#EF4444")

    def _screen_ocr_worker(self):
        try:
            recognized_text = recognize_screen_text()
            logger.info("Screen OCR completed; recognized %d characters", len(recognized_text))
            self._ocr_results.put((recognized_text, None))
        except Exception as exc:
            logger.exception("F10 screen OCR failed")
            self._ocr_results.put((None, str(exc)))

    def _apply_ocr_result(self):
        try:
            recognized_text, error = self._ocr_results.get_nowait()
        except queue.Empty:
            return

        self._ocr_in_progress = False
        if error:
            logger.error("Screen OCR result failed: %s", error)
            self.show_message(f"Screen OCR failed: {error}", "#EF4444")
            return
        if not recognized_text:
            logger.warning("Screen OCR completed without readable text")
            self.show_message("No readable text found on screen.", "#EF4444")
            return

        self.deiconify()
        self.attributes("-topmost", True)
        self.focus_force()
        self.attributes("-topmost", False)
        self.search_entry.delete(0, 'end')
        self.search_entry.insert(0, recognized_text)
        self.search_entry.focus_set()
        logger.info("Inserted OCR text into search field (%d characters)", len(recognized_text))
        self.show_message("Screen text recognized. Review it and press Search.", "#10B981")

    def _process_clipboard_search(self):
        if self._closing or self.controller is None or self.controller.is_busy:
            logger.info("Skipped F9 search: app closing, controller missing, or request busy")
            return
        logger.info("Processing F9 clipboard search")
        try:
            clipboard_text = pyperclip.paste()
        except Exception:
            logging.getLogger(__name__).exception("Could not read clipboard")
            self.show_message("Could not read the clipboard. Try again or enter a query manually.", "#EF4444")
            return
        if not isinstance(clipboard_text, str):
            self.show_message("Clipboard does not contain text.", "#EF4444")
            return
        query = clipboard_text.strip()
        if not query:
            logger.info("F9 clipboard did not contain searchable text")
            self.show_message("Clipboard is empty.", "#EF4444")
            return

        logger.info("Starting F9 search with %d characters", len(query))

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
            card = ctk.CTkFrame(self.results_frame, fg_color="#2A2D34", corner_radius=12)
            card.grid(row=index, column=0, padx=5, pady=5, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            self.result_widgets.append(card)
            label = self._wrapped_label(card, quiz["title"], self.font_bold)
            label.grid(row=0, column=0, padx=15, pady=(12, 4), sticky="ew")
            identifier = self._wrapped_label(card, f"UUID: {quiz['uuid']}", self.font_main, "#A0AEC0")
            identifier.grid(row=1, column=0, padx=15, pady=(0, 12), sticky="ew")
            button = ctk.CTkButton(
                card, text="Open", width=80,
                command=lambda u=quiz["uuid"]: self.controller.handle_fetch(u) if self.controller else None,
            )
            button.grid(row=0, column=1, rowspan=2, padx=15, pady=12)

    def _wrapped_label(self, parent, text, font, color="#FFFFFF"):
        label = ctk.CTkLabel(
            parent, text=text, font=font, text_color=color, width=1,
            wraplength=100, justify="left", anchor="w",
        )
        last_width = None

        def resize(event):
            nonlocal last_width
            width = max(20, int(event.width / label._get_widget_scaling()) - 4)
            if width != last_width:
                last_width = width
                label.configure(wraplength=width)
        Misc.bind(label, "<Configure>", resize, add="+")
        return label

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

            q_label = self._wrapped_label(
                card, f"{index + 1}. [{item.get('type', 'unknown')}] {item['question']}",
                self.font_question,
            )
            q_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="ew")

            details = "\n".join(filter(None, (item.get("message"), item.get("warning"))))
            if details:
                warning_label = self._wrapped_label(
                    card, details, self.font_main,
                    "#FBBF24" if item.get("warning") else "#A0AEC0",
                )
                warning_label.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

            if not item["answers"]:
                empty_text = {
                    "content": "Content slide", "no_answer_required": "No correct answer required",
                    "unsupported": "Unsupported format", "invalid_data": "Answers unavailable",
                    "no_correct_answer": "No correct answer specified",
                }.get(item.get("status"), "Answers unavailable")
                label = self._wrapped_label(card, empty_text, self.font_main, "#A0AEC0")
                label.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="ew")

            for answer_index, answer in enumerate(item["answers"]):
                row = ctk.CTkFrame(card, fg_color="#1E1F24", corner_radius=8)
                row.grid(row=answer_index + 2, column=0, padx=20, pady=(5, 10), sticky="ew")
                row.grid_columnconfigure(0, weight=1)
                label = self._wrapped_label(row, answer, self.font_bold, "#6EE7B7")
                label.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
                button = ctk.CTkButton(
                    row, text="Copy", width=75, fg_color="#10B981", hover_color="#059669",
                    command=lambda a=answer: self.controller.handle_copy(a) if self.controller else None,
                )
                button.grid(row=0, column=1, padx=12, pady=12, sticky="n")


