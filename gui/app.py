import logging
import queue
import threading
import os
import sys
import keyboard
import pyperclip
from tkinter import Canvas, Misc, TclError, Toplevel, filedialog
import customtkinter as ctk
from core.ocr import capture_primary_screen, crop_selection, recognize_image_text

logger = logging.getLogger(__name__)

COLORS = {
    "background": "#111315",
    "panel": "#191B1F",
    "surface": "#1D2024",
    "input": "#15171A",
    "border": "#2B2F34",
    "text": "#E6E8EB",
    "muted": "#A1A7AF",
    "button": "#343D49",
    "button_hover": "#414D5D",
    "secondary_button": "#2B2F34",
    "secondary_hover": "#3A3F46",
    "copy_button": "#254137",
    "copy_hover": "#315444",
    "answer_text": "#A8D5C0",
}


def _filter_question_results(questions, query):
    normalized_query = query.strip().casefold()
    return [
        (index, item)
        for index, item in enumerate(questions)
        if normalized_query in item["question"].casefold()
    ]


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
        self.configure(fg_color=COLORS["background"])
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        icon_path = get_resource_path("icon.ico")
        try:
            self.iconbitmap(default=icon_path)
        except TclError as exc:
            logger.warning("Could not load window icon %s: %s", icon_path, exc)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self._closing = False
        self._hotkey_pending = threading.Event()
        self._capture_pending = threading.Event()
        self._ocr_results = queue.Queue()
        self._ocr_in_progress = False
        self._screen_snapshot = None
        self._selection_overlay = None
        self._selection_canvas = None
        self._selection_image = None
        self._selection_start = None
        self._selection_rect = None
        self._selection_display_size = None
        self._poll_id = None
        self._hotkey_handle = None
        self._capture_hotkey_handle = None
        self.controller = None
        self.result_widgets = []


        self.font_title = ctk.CTkFont(family="Segoe UI", size=28, weight="bold")
        self.font_main = ctk.CTkFont(family="Segoe UI", size=15)
        self.font_bold = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        self.font_question = ctk.CTkFont(family="Segoe UI", size=17, weight="bold")


        self.header_label = ctk.CTkLabel(self, text="Kahoot Reincarnation Parser", font=self.font_title, text_color=COLORS["text"])
        self.header_label.grid(row=0, column=0, padx=20, pady=(30, 10), sticky="w")


        self.search_frame = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=12)
        self.search_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.search_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            self.search_frame, 
            placeholder_text="Enter quiz title or paste a question...", 
            font=self.font_main,
            height=45,
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["input"]
        )
        self.search_entry.grid(row=0, column=0, padx=(15, 10), pady=15, sticky="ew")
        self.search_entry.bind("<Return>", lambda event: self._on_search_clicked())

        self.search_button = ctk.CTkButton(
            self.search_frame, 
            text="Search", 
            font=self.font_bold, 
            height=45,
            corner_radius=8,
            fg_color=COLORS["button"],
            hover_color=COLORS["button_hover"],
            command=self._on_search_clicked
        )
        self.search_button.grid(row=0, column=1, padx=(0, 10), pady=15)

        self.export_button = ctk.CTkButton(
            self.search_frame, 
            text="Export JSON", 
            font=self.font_bold, 
            height=45,
            corner_radius=8,
            fg_color=COLORS["secondary_button"],
            hover_color=COLORS["secondary_hover"],
            state="disabled", 
            command=self._on_export_clicked
        )
        self.export_button.grid(row=0, column=2, padx=(0, 15), pady=15)


        self.status_label = ctk.CTkLabel(self, text="F9: search clipboard. F10: select a screen region for OCR.", font=self.font_main, text_color=COLORS["muted"])
        self.status_label.grid(row=2, column=0, padx=25, pady=(0, 10), sticky="w")

        self.results_frame = ctk.CTkFrame(self, fg_color=COLORS["background"], corner_radius=0)
        self.results_frame.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.results_frame.grid_columnconfigure(0, weight=1)
        self.results_frame.grid_rowconfigure(0, weight=1)

        self._result_mode = None
        self._result_data = []
        self._question_cards = []
        self._no_questions_label = None
        self.question_search_frame = ctk.CTkFrame(
            self, fg_color=COLORS["background"], corner_radius=0
        )
        self.question_search_frame.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="ew")
        self.question_search_frame.grid_columnconfigure(0, weight=1)
        self.question_search_entry = ctk.CTkEntry(
            self.question_search_frame,
            placeholder_text="Find in quiz questions... (Ctrl+F)",
            font=self.font_main,
            height=38,
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["input"],
        )
        self.question_search_entry.grid(row=0, column=0, sticky="ew")
        self.question_search_entry.bind(
            "<KeyRelease>", self._on_question_search_changed
        )
        self.question_search_entry.bind("<Escape>", self._clear_question_search)
        self.question_search_frame.grid_remove()

        self.results_content = ctk.CTkScrollableFrame(
            self.results_frame,
            fg_color=COLORS["background"],
            corner_radius=0,
        )
        self.results_content.grid(row=0, column=0, sticky="nsew")
        self.results_content.grid_columnconfigure(0, weight=1)
        self.bind("<Control-f>", self._focus_question_search)
        self.bind("<Control-F>", self._focus_question_search)

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
        self._close_selection_overlay()
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
        """Capture the desktop and let the user select the question region."""
        if (
            self._closing
            or self.controller is None
            or self.controller.is_busy
            or self._ocr_in_progress
        ):
            logger.info("Skipped OCR start: app closing, controller missing, request busy, or OCR active")
            return
        self._ocr_in_progress = True
        logger.info("Starting screen region selection")
        self.show_message("Select the question area on screen. Press Esc to cancel.", "#A0AEC0")
        try:
            self._screen_snapshot = capture_primary_screen()
            self._open_selection_overlay()
        except Exception:
            self._ocr_in_progress = False
            self._screen_snapshot = None
            logger.exception("Could not open screen region selector")
            self.show_message("Could not capture the screen. See kahoot_parser.log.", "#EF4444")

    def _open_selection_overlay(self):
        from PIL import Image, ImageTk

        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        if width <= 0 or height <= 0:
            raise RuntimeError("Could not determine primary monitor dimensions")

        preview = self._screen_snapshot.resize((width, height), Image.Resampling.LANCZOS)
        overlay = Toplevel(self)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"{width}x{height}+0+0")
        canvas = Canvas(overlay, width=width, height=height, highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        self._selection_image = ImageTk.PhotoImage(preview)
        canvas.create_image(0, 0, image=self._selection_image, anchor="nw")
        canvas.create_rectangle(12, 12, 600, 52, fill="#111827", outline="#111827")
        canvas.create_text(
            24, 32,
            text="Drag around the question, release to OCR • Esc cancels",
            fill="white", anchor="w", font=("Segoe UI", 14, "bold"),
        )
        canvas.bind("<ButtonPress-1>", self._selection_mouse_down)
        canvas.bind("<B1-Motion>", self._selection_mouse_move)
        canvas.bind("<ButtonRelease-1>", self._selection_mouse_up)
        overlay.bind("<Escape>", lambda _event: self._cancel_screen_selection())
        overlay.protocol("WM_DELETE_WINDOW", self._cancel_screen_selection)
        overlay._ocr_photo = self._selection_image
        self._selection_overlay = overlay
        self._selection_canvas = canvas
        self._selection_display_size = (width, height)
        overlay.grab_set()
        overlay.focus_force()
        logger.info("Screen region selector opened at %dx%d", width, height)

    def _selection_mouse_down(self, event):
        self._selection_start = (event.x, event.y)
        if self._selection_rect is not None:
            self._selection_canvas.delete(self._selection_rect)
        self._selection_rect = self._selection_canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#22D3EE", width=3,
        )

    def _selection_mouse_move(self, event):
        if self._selection_start is None or self._selection_rect is None:
            return
        self._selection_canvas.coords(
            self._selection_rect,
            self._selection_start[0], self._selection_start[1], event.x, event.y,
        )

    def _selection_mouse_up(self, event):
        if self._selection_start is None or self._screen_snapshot is None:
            return
        start = self._selection_start
        self._selection_start = None
        try:
            image_crop = crop_selection(
                self._screen_snapshot,
                start,
                (event.x, event.y),
                self._selection_display_size,
            )
        except ValueError as exc:
            logger.info("Screen selection rejected: %s", exc)
            self._cancel_screen_selection(str(exc))
            return

        logger.info("Selected screen region with dimensions %s", image_crop.size)
        self._screen_snapshot = None
        self._close_selection_overlay()
        self.show_message("Recognizing selected area…", "#A0AEC0")
        try:
            logger.info("Starting OCR worker for selected region")
            threading.Thread(
                target=self._screen_ocr_worker,
                args=(image_crop,),
                daemon=True,
            ).start()
        except RuntimeError:
            self._ocr_in_progress = False
            logger.exception("Could not start OCR worker")
            self.show_message("Could not start OCR. See kahoot_parser.log.", "#EF4444")

    def _cancel_screen_selection(self, message="Screen selection cancelled."):
        logger.info("Screen region selection cancelled")
        self._screen_snapshot = None
        self._selection_start = None
        self._close_selection_overlay()
        self._ocr_in_progress = False
        if not self._closing:
            self.show_message(message, "#D97706")

    def _close_selection_overlay(self):
        overlay = self._selection_overlay
        self._selection_overlay = None
        self._selection_canvas = None
        self._selection_image = None
        self._selection_rect = None
        if overlay is not None:
            try:
                overlay.grab_release()
                overlay.destroy()
            except TclError:
                pass

    def _screen_ocr_worker(self, image_crop):
        try:
            recognized_text = recognize_image_text(image_crop)
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
        for widget in self.results_content.winfo_children():
            widget.destroy()
        self.result_widgets.clear()
        self._result_mode = None
        self._result_data = []
        self._question_cards.clear()
        self._no_questions_label = None
        self.question_search_entry.delete(0, "end")
        self.question_search_frame.grid_remove()
        self.export_button.configure(state="disabled")

    def show_loading(self, message):
        self.clear_results()
        self.status_label.configure(text=message, text_color=COLORS["text"])
        self.search_button.configure(state="disabled")
        self.search_entry.configure(state="disabled")

    def show_message(self, message, color):
        muted_status_colors = {
            "#EF4444": "#D98C8C",
            "#D97706": "#C99D68",
            "#10B981": "#8BC9A9",
            "#FFFFFF": COLORS["text"],
            "#A0AEC0": COLORS["muted"],
        }
        self.status_label.configure(text=message, text_color=muted_status_colors.get(color, color))
        state = "disabled" if self.controller and self.controller.is_busy else "normal"
        self.search_button.configure(state=state)
        self.search_entry.configure(state=state)

    def display_search_results(self, quizzes):
        self.search_button.configure(state="normal")
        if not quizzes:
            self.clear_results()
            self.show_message("No public quizzes found for this query.", "#EF4444")
            return

        self.clear_results()
        self._result_mode = "search"
        self._result_data = quizzes
        self.show_message(f"Found {len(quizzes)} quizzes. Select one to extract answers.", "#10B981")
        self._render_result_page()

    def _focus_question_search(self, _event=None):
        if self._result_mode != "answers" or self._closing:
            return
        self.question_search_entry.focus_set()
        self.question_search_entry.select_range(0, "end")
        return "break"

    def _on_question_search_changed(self, _event=None):
        if self._result_mode == "answers":
            self._filter_visible_question_cards()

    def _clear_question_search(self, _event=None):
        if self.question_search_entry.get():
            self.question_search_entry.delete(0, "end")
        self._filter_visible_question_cards()
        return "break"

    def _render_result_page(self):
        for widget in self.results_content.winfo_children():
            widget.destroy()
        self.result_widgets.clear()
        self._question_cards.clear()
        self._no_questions_label = None
        if not self._result_data:
            return

        if self._result_mode == "answers":
            self.question_search_frame.grid()
            for index, item in enumerate(self._result_data):
                card = ctk.CTkFrame(
                    self.results_content, fg_color=COLORS["panel"], corner_radius=12
                )
                card.grid(row=index, column=0, padx=5, pady=8, sticky="ew")
                card.grid_columnconfigure(0, weight=1)
                self.result_widgets.append(card)
                self._question_cards.append((index, item["question"], card))
                self._render_question_card(card, item, index)
            self._no_questions_label = ctk.CTkLabel(
                self.results_content,
                text="No questions match your search.",
                font=self.font_main,
                text_color=COLORS["muted"],
            )
            self._no_questions_label.grid_remove()
            self._filter_visible_question_cards()
        else:
            self.question_search_frame.grid_remove()
            for row, quiz in enumerate(self._result_data):
                card = ctk.CTkFrame(
                    self.results_content, fg_color=COLORS["panel"], corner_radius=12
                )
                card.grid(row=row, column=0, padx=5, pady=8, sticky="ew")
                card.grid_columnconfigure(0, weight=1)
                self.result_widgets.append(card)
                self._render_quiz_card(card, quiz)

    def _filter_visible_question_cards(self):
        matches = {
            index
            for index, _item in _filter_question_results(
                self._result_data, self.question_search_entry.get()
            )
        }
        visible_row = 0
        for index, _question, card in self._question_cards:
            if index in matches:
                card.grid_configure(row=visible_row)
                visible_row += 1
            else:
                card.grid_remove()

        if self._no_questions_label is not None:
            if visible_row:
                self._no_questions_label.grid_remove()
            else:
                self._no_questions_label.grid(row=0, column=0, pady=24)
        self.results_content._parent_canvas.yview_moveto(0)

    def _render_quiz_card(self, card, quiz):
        title = self._wrapped_label(card, quiz["title"], self.font_bold, COLORS["text"])
        title.grid(row=0, column=0, padx=20, pady=(24, 8), sticky="ew")
        identifier = self._wrapped_label(
            card, f"UUID: {quiz['uuid']}", self.font_main, COLORS["muted"]
        )
        identifier.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        button = ctk.CTkButton(
            card,
            text="Open quiz",
            width=110,
            fg_color=COLORS["button"],
            hover_color=COLORS["button_hover"],
            command=lambda u=quiz["uuid"]: self.controller.handle_fetch(u) if self.controller else None,
        )
        button.grid(row=0, column=1, rowspan=2, padx=20, pady=20)

    def _render_question_card(self, card, item, index):
        question = self._wrapped_label(
            card,
            f"{index + 1}. [{item.get('type', 'unknown')}] {item['question']}",
            self.font_question,
            COLORS["text"],
        )
        question.grid(row=0, column=0, padx=20, pady=(22, 10), sticky="ew")

        next_row = 1
        details = "\n".join(filter(None, (item.get("message"), item.get("warning"))))
        if details:
            details_label = self._wrapped_label(
                card,
                details,
                self.font_main,
                "#C99D68" if item.get("warning") else COLORS["muted"],
            )
            details_label.grid(row=next_row, column=0, padx=20, pady=6, sticky="ew")
            next_row += 1

        if not item["answers"]:
            empty_text = {
                "content": "Content slide",
                "no_answer_required": "No correct answer required",
                "unsupported": "Unsupported format",
                "invalid_data": "Answers unavailable",
                "no_correct_answer": "No correct answer specified",
            }.get(item.get("status"), "Answers unavailable")
            empty_label = self._wrapped_label(card, empty_text, self.font_main, COLORS["muted"])
            empty_label.grid(row=next_row, column=0, padx=20, pady=(12, 22), sticky="ew")
            return

        for answer_index, answer in enumerate(item["answers"]):
            answer_row = ctk.CTkFrame(card, fg_color=COLORS["surface"], corner_radius=8)
            answer_row.grid(
                row=next_row + answer_index,
                column=0,
                padx=20,
                pady=(5, 7),
                sticky="ew",
            )
            answer_row.grid_columnconfigure(0, weight=1)
            label = self._wrapped_label(
                answer_row, answer, self.font_bold, COLORS["answer_text"]
            )
            label.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
            button = ctk.CTkButton(
                answer_row,
                text="Copy",
                width=75,
                fg_color=COLORS["copy_button"],
                hover_color=COLORS["copy_hover"],
                command=lambda value=answer: self.controller.handle_copy(value) if self.controller else None,
            )
            button.grid(row=0, column=1, padx=12, pady=12, sticky="n")

    def display_quiz_answers(self, answers_data):
        self.search_button.configure(state="normal")
        if not answers_data:
            self.clear_results()
            self.show_message("No questions were returned for this quiz.", "#EF4444")
            return

        self.clear_results()
        self.export_button.configure(state="normal")
        self._result_mode = "answers"
        self._result_data = answers_data
        warning_count = sum(bool(item.get("warning")) for item in answers_data)
        unsupported_count = sum(item.get("status") == "unsupported" for item in answers_data)
        self.show_message(
            f"Loaded {len(answers_data)} items. "
            f"Unsupported: {unsupported_count}. Data warnings: {warning_count}.",
            "#D97706" if warning_count or unsupported_count else "#10B981",
        )
        self._render_result_page()

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
