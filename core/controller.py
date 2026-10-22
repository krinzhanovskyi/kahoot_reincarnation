import logging
import threading
import json
import pyperclip
from api.client import KahootAPIError
from api.search import search_quizzes
from api.fetch import get_quiz_answers

logger = logging.getLogger(__name__)


class KahootController:
    def __init__(self, view):
        self.view = view
        self.current_quiz_data = []

    def handle_search(self, query):
        if not query:
            self.view.show_message("Please enter a search query.", "#EF4444")
            return
        self.view.show_loading("Searching API...")
        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query):
        try:
            quizzes = search_quizzes(query)
        except Exception as exc:
            self._report_worker_error(exc)
            return
        self.view.after(0, self.view.display_search_results, quizzes)

    def handle_fetch(self, uuid):
        self.current_quiz_data = []
        self.view.show_loading("Fetching and parsing JSON...")
        threading.Thread(target=self._fetch_worker, args=(uuid,), daemon=True).start()

    def _fetch_worker(self, uuid):
        try:
            answers_data = get_quiz_answers(uuid)
        except Exception as exc:
            self._report_worker_error(exc)
            return
        self.current_quiz_data = answers_data
        self.view.after(0, self.view.display_quiz_answers, answers_data)

    def _report_worker_error(self, exc):
        # This boundary catches unexpected bugs too, so loading can finish.
        logger.exception("Kahoot operation failed")
        if isinstance(exc, KahootAPIError):
            message = str(exc)
        else:
            message = "Unexpected error while processing quiz data. Check the console log."
        self.view.after(0, self.view.show_message, message, "#EF4444")

    def handle_copy(self, text):
        pyperclip.copy(text)
        self.view.show_message("Answer copied to clipboard!", "#3B82F6")

    def handle_export(self, file_path):
        if not self.current_quiz_data or not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.current_quiz_data, f, ensure_ascii=False, indent=4)
            self.view.show_message(f"Exported successfully to {file_path}", "#10B981")
        except Exception:
            self.view.show_message("Failed to export file.", "#EF4444")
