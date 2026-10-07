import customtkinter as ctk
from api.search import search_quizzes
from api.fetch import get_quiz_answers

class KahootParserApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Kahoot Public API Parser")
        self.geometry("900x700")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.search_frame = ctk.CTkFrame(self)
        self.search_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        self.search_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Enter quiz title...", font=("Arial", 14))
        self.search_entry.grid(row=0, column=0, padx=(10, 10), pady=10, sticky="ew")
        self.search_entry.bind("<Return>", lambda event: self.perform_search())

        self.search_button = ctk.CTkButton(self.search_frame, text="Search", font=("Arial", 14, "bold"), command=self.perform_search)
        self.search_button.grid(row=0, column=1, padx=(0, 10), pady=10)

        self.status_label = ctk.CTkLabel(self, text="", font=("Arial", 14))
        self.status_label.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="w")

        self.results_frame = ctk.CTkScrollableFrame(self)
        self.results_frame.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.results_frame.grid_columnconfigure(0, weight=1)

        self.result_widgets = []

    def clear_results(self):
        for widget in self.result_widgets:
            widget.destroy()
        self.result_widgets.clear()

    def perform_search(self):
        self.clear_results()
        query = self.search_entry.get().strip()
        
        if not query:
            self.status_label.configure(text="Please enter a search query.", text_color="#FF4C4C")
            return

        self.status_label.configure(text="Searching API...", text_color="#FFFFFF")
        self.update()

        quizzes = search_quizzes(query)

        if not quizzes:
            self.status_label.configure(text="No public quizzes found or API is restricting access.", text_color="#FF4C4C")
            return

        self.status_label.configure(text=f"Found {len(quizzes)} quizzes. Click one to extract answers.", text_color="#00FF7F")

        for index, quiz in enumerate(quizzes):
            btn = ctk.CTkButton(
                self.results_frame,
                text=f"{quiz['title']}  |  UUID: {quiz['uuid']}",
                font=("Arial", 14),
                anchor="w",
                fg_color="#2B2B2B",
                hover_color="#3A3A3A",
                command=lambda u=quiz["uuid"]: self.fetch_and_display_answers(u)
            )
            btn.grid(row=index, column=0, padx=10, pady=5, sticky="ew")
            self.result_widgets.append(btn)

    def fetch_and_display_answers(self, uuid):
        self.clear_results()
        self.status_label.configure(text="Fetching and parsing JSON...", text_color="#FFFFFF")
        self.update()

        answers_data = get_quiz_answers(uuid)

        if not answers_data:
            self.status_label.configure(text="Failed to parse quiz data. The quiz might be private.", text_color="#FF4C4C")
            return

        self.status_label.configure(text=f"Successfully extracted {len(answers_data)} questions.", text_color="#00FF7F")

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

            answers_text = "  |  ".join(item['answers']) if item['answers'] else "No correct answer specified in JSON"
            a_label = ctk.CTkLabel(
                self.results_frame,
                text=f"A: {answers_text}",
                font=("Arial", 15),
                text_color="#00FF7F",
                wraplength=800,
                justify="left"
            )
            a_label.grid(row=index * 2 + 1, column=0, padx=10, pady=(5, 5), sticky="w")
            self.result_widgets.append(a_label)