import threading
import json
import keyboard
import pyperclip
from tkinter import filedialog
import customtkinter as ctk
from api.search import search_quizzes
from api.fetch import get_quiz_answers

class KahootParserApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Kahoot Public API Parser")
        self.geometry("900x750")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.current_quiz_data = []

        self.search_frame = ctk.CTkFrame(self)
        self.search_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        self.search_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Enter quiz title or question...", font=("Arial", 14))
        self.search_entry.grid(row=0, column=0, padx=(10, 10), pady=10, sticky="ew")
        self.search_entry.bind("<Return>", lambda event: self.start_search_thread())

        self.search_button = ctk.CTkButton(self.search_frame, text="Search", font=("Arial", 14, "bold"), command=self.start_search_thread)
        self.search_button.grid(row=0, column=1, padx=(0, 10), pady=10)

        self.export_button = ctk.CTkButton(
            self.search_frame, 
            text="Export JSON", 
            font=("Arial", 14, "bold"), 
            fg_color="#D97706", 
            hover_color="#B45309", 
            state="disabled", 
            command=self.export_to_json
        )
        self.export_button.grid(row=0, column=2, padx=(0, 10), pady=10)

        self.status_label = ctk.CTkLabel(self, text="", font=("Arial", 14))
        self.status_label.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="w")

        self.results_frame = ctk.CTkScrollableFrame(self)
        self.results_frame.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.results_frame.grid_columnconfigure(0, weight=1)

        self.result_widgets = []

        keyboard.add_hotkey("F12", self.on_hotkey_pressed)

    def on_hotkey_pressed(self):
        self.after(0, self.process_hotkey)

    def process_hotkey(self):
        self.deiconify()
        self.attributes("-topmost", True)
        self.attributes("-topmost", False)
        self.lift()
        self.focus_force()

        copied_text = pyperclip.paste().strip()
        if copied_text:
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, copied_text)
            self.start_search_thread()

    def on_closing(self):
        keyboard.unhook_all()
        self.quit()
        self.destroy()

    def clear_results(self):
        for widget in self.result_widgets:
            widget.destroy()
        self.result_widgets.clear()
        self.current_quiz_data = []
        self.export_button.configure(state="disabled")

    def set_ui_state(self, message, color, disable_button=False):
        self.status_label.configure(text=message, text_color=color)
        state = "disabled" if disable_button else "normal"
        self.search_button.configure(state=state)
        self.update()

    def start_search_thread(self):
        query = self.search_entry.get().strip()
        if not query:
            self.set_ui_state("Please enter a search query.", "#FF4C4C")
            return

        self.clear_results()
        self.set_ui_state("Searching API...", "#FFFFFF", disable_button=True)

        threading.Thread(target=self._perform_search, args=(query,), daemon=True).start()

    def _perform_search(self, query):
        quizzes = search_quizzes(query)
        self.after(0, self._render_search_results, quizzes)

    def _render_search_results(self, quizzes):
        self.search_button.configure(state="normal")

        if not quizzes:
            self.set_ui_state("No public quizzes found or API is restricting access.", "#FF4C4C")
            return

        self.set_ui_state(f"Found {len(quizzes)} quizzes. Click one to extract answers.", "#00FF7F")

        for index, quiz in enumerate(quizzes):
            btn = ctk.CTkButton(
                self.results_frame,
                text=f"{quiz['title']}  |  UUID: {quiz['uuid']}",
                font=("Arial", 14),
                anchor="w",
                fg_color="#2B2B2B",
                hover_color="#3A3A3A",
                command=lambda u=quiz["uuid"]: self.start_fetch_thread(u)
            )
            btn.grid(row=index, column=0, padx=10, pady=5, sticky="ew")
            self.result_widgets.append(btn)

    def start_fetch_thread(self, uuid):
        self.clear_results()
        self.set_ui_state("Fetching and parsing JSON...", "#FFFFFF", disable_button=True)
        threading.Thread(target=self._perform_fetch, args=(uuid,), daemon=True).start()

    def _perform_fetch(self, uuid):
        answers_data = get_quiz_answers(uuid)
        self.after(0, self._render_fetch_results, answers_data)

    def _render_fetch_results(self, answers_data):
        self.search_button.configure(state="normal")
        
        if not answers_data:
            self.set_ui_state("Failed to parse quiz data. The quiz might be private.", "#FF4C4C")
            return

        self.current_quiz_data = answers_data
        self.export_button.configure(state="normal")
        self.set_ui_state(f"Successfully extracted {len(answers_data)} questions. Click an answer to copy it.", "#00FF7F")

        for index, item in enumerate(answers_data):
            q_label = ctk.CTkLabel(
                self.results_frame,
                text=f"Q{index + 1}: {item['question']}",
                font=("Arial", 16, "bold"),
                wraplength=800,
                justify="left"
            )
            q_label.grid(row=index * 2, column=0, padx=10, pady=(20, 0), sticky="w")
            self.result_widgets.append(q_label)

            answers_text = "  |  ".join(item['answers']) if item['answers'] else "No correct answer specified"
            
            a_btn = ctk.CTkButton(
                self.results_frame,
                text=f"A: {answers_text}",
                font=("Arial", 15),
                text_color="#00FF7F",
                fg_color="transparent",
                hover_color="#2B2B2B",
                anchor="w",
                command=lambda a=answers_text: self.copy_to_clipboard(a)
            )
            a_btn.grid(row=index * 2 + 1, column=0, padx=10, pady=(5, 5), sticky="w")
            self.result_widgets.append(a_btn)

    def copy_to_clipboard(self, text):
        pyperclip.copy(text)
        self.status_label.configure(text="Answer copied to clipboard!", text_color="#3B82F6")

    def export_to_json(self):
        if not self.current_quiz_data:
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save Quiz Answers"
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(self.current_quiz_data, f, ensure_ascii=False, indent=4)
                self.set_ui_state(f"Exported successfully to {file_path}", "#00FF7F")
            except Exception:
                self.set_ui_state("Failed to export file.", "#FF4C4C")