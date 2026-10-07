from tkinter import filedialog
import customtkinter as ctk
import keyboard
import pyperclip

class KahootParserApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Kahoot API Parser")
        self.geometry("950x800")
        self.configure(fg_color="#1A1A1A")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.controller = None
        self.result_widgets = []

        self.font_title = ctk.CTkFont(family="Segoe UI", size=28, weight="bold")
        self.font_main = ctk.CTkFont(family="Segoe UI", size=15)
        self.font_bold = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        self.font_question = ctk.CTkFont(family="Segoe UI", size=17, weight="bold")

        self.header_label = ctk.CTkLabel(self, text="Kahoot Public Parser", font=self.font_title, text_color="#FFFFFF")
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

        keyboard.add_hotkey('F9', self._on_hotkey_press)

    def set_controller(self, controller):
        self.controller = controller

    def on_closing(self):
        keyboard.unhook_all()
        self.quit()
        self.destroy()

    def _on_hotkey_press(self):
        self.after(0, self._process_clipboard_search)

    def _process_clipboard_search(self):
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
        self.update()

    def show_message(self, message, color):
        self.status_label.configure(text=message, text_color=color)
        self.search_button.configure(state="normal")

    def display_search_results(self, quizzes):
        self.search_button.configure(state="normal")
        
        if not quizzes:
            self.show_message("No public quizzes found or API is restricting access.", "#EF4444")
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
            self.show_message("Failed to parse quiz data. The quiz might be private.", "#EF4444")
            return

        self.export_button.configure(state="normal")
        self.show_message(f"Extracted {len(answers_data)} questions. Click an answer to copy it.", "#10B981")

        for index, item in enumerate(answers_data):
            card = ctk.CTkFrame(self.results_frame, fg_color="#2A2D34", corner_radius=12)
            card.grid(row=index, column=0, padx=5, pady=10, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            self.result_widgets.append(card)

            q_label = ctk.CTkLabel(
                card,
                text=f"Q{index + 1}: {item['question']}",
                font=self.font_question,
                text_color="#FFFFFF",
                wraplength=800,
                justify="left"
            )
            q_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")

            answers_text = "  |  ".join(item['answers']) if item['answers'] else "No correct answer specified"
            
            a_btn = ctk.CTkButton(
                card,
                text=f"Copy Answer: {answers_text}",
                font=self.font_bold,
                height=35,
                corner_radius=6,
                text_color="#FFFFFF",
                fg_color="#10B981",
                hover_color="#059669",
                anchor="w",
                command=lambda a=answers_text: self.controller.handle_copy(a) if self.controller else None
            )
            a_btn.grid(row=1, column=0, padx=20, pady=(10, 20), sticky="w")