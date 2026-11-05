import tkinter as tk

import customtkinter as ctk


EMPTY_TEXT = {
    "content": "Content slide",
    "no_answer_required": "No correct answer required",
    "unsupported": "Unsupported format",
    "invalid_data": "Answers unavailable",
    "no_correct_answer": "No correct answer specified",
}


class QuizView(ctk.CTkFrame):
    def __init__(self, master, on_copy, colors, font_family="Segoe UI"):
        super().__init__(master, fg_color=colors["background"], corner_radius=0)
        self._on_copy = on_copy
        self._colors = colors
        self._answers = []
        self._question_ranges = []
        self._matches = []
        self._current = -1
        self._find_job = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.find_entry = ctk.CTkEntry(
            self,
            placeholder_text="Find in quiz questions... (Ctrl+F, Enter = next, Esc = clear)",
            height=38,
            corner_radius=8,
            border_width=1,
            border_color=colors["border"],
            fg_color=colors["input"],
        )
        self.find_entry.grid(row=0, column=0, padx=(0, 8), pady=(0, 8), sticky="ew")
        self.counter_label = ctk.CTkLabel(
            self, text="", text_color=colors["muted"], width=70
        )
        self.counter_label.grid(row=0, column=1, padx=(0, 4), pady=(0, 8))

        self.text = tk.Text(
            self,
            wrap="word",
            bg=colors["background"],
            fg=colors["text"],
            bd=0,
            highlightthickness=0,
            padx=16,
            pady=8,
            cursor="arrow",
            font=(font_family, 11),
            selectbackground=colors["button"],
            insertwidth=0,
            takefocus=0,
        )
        self.text.grid(row=1, column=0, padx=(0, 4), sticky="nsew")
        scrollbar = ctk.CTkScrollbar(self, command=self.text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set, state="disabled")

        self.text.tag_configure("gap", font=(font_family, 7))
        self.text.tag_configure(
            "question", font=(font_family, 12, "bold"), foreground=colors["text"]
        )
        self.text.tag_configure(
            "meta", foreground=colors["muted"], lmargin1=16, lmargin2=16
        )
        self.text.tag_configure(
            "warning", foreground="#C99D68", lmargin1=16, lmargin2=16
        )
        self.text.tag_configure(
            "empty", foreground=colors["muted"], lmargin1=16, lmargin2=16
        )
        self.text.tag_configure(
            "answer",
            foreground=colors["answer_text"],
            font=(font_family, 11, "bold"),
            lmargin1=16,
            lmargin2=96,
        )
        self.text.tag_configure(
            "copy",
            background=colors["copy_button"],
            foreground=colors["text"],
            font=(font_family, 9, "bold"),
        )
        self.text.tag_configure(
            "match", background="#FACC15", foreground="#111827"
        )
        self.text.tag_configure(
            "current", background="#F97316", foreground="#111827"
        )
        self.text.tag_bind("copy", "<Enter>", lambda _event: self.text.configure(cursor="hand2"))
        self.text.tag_bind("copy", "<Leave>", lambda _event: self.text.configure(cursor="arrow"))
        self.text.tag_bind("copy", "<Button-1>", self._on_copy_click)

        self.find_entry.bind("<KeyRelease>", self._schedule_find)
        self.find_entry.bind("<Return>", lambda _event: self.next_match(1))
        self.find_entry.bind("<Shift-Return>", lambda _event: self.next_match(-1))
        self.find_entry.bind("<Escape>", lambda _event: self.clear_find())
        self.winfo_toplevel().bind("<Control-f>", self._focus_find, add="+")
        self.winfo_toplevel().bind("<Control-F>", self._focus_find, add="+")

    def render(self, items):
        self.clear_find()
        self._answers.clear()
        self._question_ranges.clear()
        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")

        for index, item in enumerate(items, start=1):
            if index > 1:
                text.insert("end", "\n", "gap")
            text.insert(
                "end",
                f"{index}. [{item.get('type', 'unknown')}] ",
                "question",
            )
            question_start = text.index("end-1c")
            text.insert("end", item["question"], "question")
            question_end = text.index("end-1c")
            self._question_ranges.append((question_start, question_end))
            text.insert("end", "\n")

            if item.get("message"):
                text.insert("end", item["message"] + "\n", "meta")
            if item.get("warning"):
                text.insert("end", item["warning"] + "\n", "warning")
            if not item["answers"]:
                empty_text = EMPTY_TEXT.get(
                    item.get("status"), "Answers unavailable"
                )
                text.insert("end", empty_text + "\n", "empty")

            for answer in item["answers"]:
                answer_index = len(self._answers)
                self._answers.append(answer)
                copy_tag = f"copy-{answer_index}"
                text.tag_configure(copy_tag, background=self._colors["copy_button"])
                text.insert("end", "  Copy  ", ("copy", copy_tag))
                text.insert("end", "   " + answer + "\n", "answer")

        text.configure(state="disabled")
        text.yview_moveto(0)

    def clear(self):
        self.render([])

    def _on_copy_click(self, event):
        index = self.text.index(f"@{event.x},{event.y}")
        for tag in self.text.tag_names(index):
            if tag.startswith("copy-"):
                answer = self._answers[int(tag[5:])]
                self._on_copy(answer)
                self.text.tag_configure(tag, background="#10B981")
                self.after(
                    300,
                    lambda copy_tag=tag: self.text.tag_configure(
                        copy_tag, background=self._colors["copy_button"]
                    ),
                )
                break
        return "break"

    def _focus_find(self, _event=None):
        if self.winfo_ismapped():
            self.find_entry.focus_set()
            self.find_entry.select_range(0, "end")
            return "break"
        return None

    def _schedule_find(self, event):
        if event.keysym in {"Return", "Escape", "Shift_L", "Shift_R"}:
            return
        if self._find_job is not None:
            self.after_cancel(self._find_job)
        self._find_job = self.after(150, self._run_find)

    def _run_find(self):
        self._find_job = None
        self.find(self.find_entry.get())

    def find(self, query):
        text = self.text
        text.tag_remove("match", "1.0", "end")
        text.tag_remove("current", "1.0", "end")
        self._matches.clear()
        self._current = -1
        query = query.strip()

        if query:
            count = tk.IntVar(master=self)
            for range_start, range_end in self._question_ranges:
                start = range_start
                while True:
                    position = text.search(
                        query,
                        start,
                        stopindex=range_end,
                        nocase=True,
                        count=count,
                    )
                    if not position or count.get() == 0:
                        break
                    end = f"{position}+{count.get()}c"
                    text.tag_add("match", position, end)
                    self._matches.append((position, end))
                    start = end
            text.tag_raise("match")
            text.tag_raise("current")

        if self._matches:
            self.next_match(1)
        else:
            self.counter_label.configure(text="0/0" if query else "")
        return len(self._matches)

    def next_match(self, step):
        if not self._matches:
            return "break"
        text = self.text
        text.tag_remove("current", "1.0", "end")
        self._current = (self._current + step) % len(self._matches)
        start, end = self._matches[self._current]
        text.tag_add("current", start, end)
        text.see(start)
        self.counter_label.configure(
            text=f"{self._current + 1}/{len(self._matches)}"
        )
        return "break"

    def clear_find(self):
        if self._find_job is not None:
            self.after_cancel(self._find_job)
            self._find_job = None
        self.find_entry.delete(0, "end")
        self.find("")
        return "break"
