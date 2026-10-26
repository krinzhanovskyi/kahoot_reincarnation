import logging
import threading
import json
from queue import Empty, Queue
import pyperclip
from api.client import KahootAPIError
from api.search import search_quizzes
from api.fetch import get_quiz_answers

logger = logging.getLogger(__name__)


class KahootController:
    def __init__(self, view):
        self.view = view
        self.current_quiz_data = []
        self._request_counter = 0
        self._active_request_id = None
        self._closed = threading.Event()
        self._result_lock = threading.Lock()
        self._results = Queue()

    @property
    def is_busy(self):
        return self._active_request_id is not None

    def handle_search(self, query):
        if self._closed.is_set() or self.is_busy:
            return
        query = query.strip()
        if not query:
            self.view.show_message("Please enter a search query.", "#EF4444")
            return
        self._start_request(self._search_worker, query, "Searching API...")

    def handle_fetch(self, uuid):
        if self._closed.is_set() or self.is_busy:
            return
        self._start_request(self._fetch_worker, uuid, "Fetching and parsing JSON...")

    def _start_request(self, worker, value, message):
        self._request_counter += 1
        request_id = self._request_counter
        self._active_request_id = request_id
        self.current_quiz_data = []
        self.view.show_loading(message)
        try:
            threading.Thread(target=worker, args=(request_id, value), daemon=True).start()
        except Exception as exc:
            self._finish_request(request_id, "error", self._error_message(exc))

    def _search_worker(self, request_id, query):
        try:
            quizzes = search_quizzes(query)
        except Exception as exc:
            self._report_worker_error(request_id, exc)
            return
        self._publish_result(request_id, "search", quizzes)

    def _fetch_worker(self, request_id, uuid):
        try:
            answers_data = get_quiz_answers(uuid)
        except Exception as exc:
            self._report_worker_error(request_id, exc)
            return
        self._publish_result(request_id, "fetch", answers_data)

    def _error_message(self, exc):
        logger.exception("Kahoot operation failed")
        if isinstance(exc, KahootAPIError):
            return str(exc)
        return "Unexpected error while processing quiz data. Check the console log."

    def _report_worker_error(self, request_id, exc):
        self._publish_result(request_id, "error", self._error_message(exc))

    def _publish_result(self, request_id, kind, result):
        with self._result_lock:
            if not self._closed.is_set():
                self._results.put((request_id, kind, result))

    def process_pending_results(self):
        """Called exclusively by the GUI thread's polling callback."""
        if self._closed.is_set():
            return
        while True:
            try:
                result = self._results.get_nowait()
            except Empty:
                return
            self._finish_request(*result)

    def close(self):
        """Invalidate work without waiting for the network; call on GUI thread."""
        with self._result_lock:
            self._closed.set()
            self._active_request_id = None
            self.current_quiz_data = []
            while True:
                try:
                    self._results.get_nowait()
                except Empty:
                    break

    def _finish_request(self, request_id, kind, result):
        if self._closed.is_set() or request_id != self._active_request_id:
            return
        self._active_request_id = None
        if kind == "error":
            self.view.show_message(result, "#EF4444")
        elif kind == "search":
            self.view.display_search_results(result)
        else:
            self.current_quiz_data = result
            self.view.display_quiz_answers(result)

    def handle_copy(self, text):
        if self._closed.is_set() or self.is_busy:
            return
        try:
            pyperclip.copy(text)
        except Exception:
            logger.exception("Could not write to clipboard")
            self.view.show_message("Could not copy the answer. Please try again.", "#EF4444")
            return
        self.view.show_message("Answer copied to clipboard!", "#3B82F6")

    def handle_export(self, file_path):
        if self._closed.is_set() or self.is_busy or not self.current_quiz_data or not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.current_quiz_data, f, ensure_ascii=False, indent=4)
            self.view.show_message(f"Exported successfully to {file_path}", "#10B981")
        except OSError:
            logger.exception("Could not write quiz export to %s", file_path)
            self.view.show_message("Failed to export file.", "#EF4444")
        except (TypeError, ValueError):
            logger.exception("Quiz data could not be serialized as JSON")
            self.view.show_message("Failed to export file.", "#EF4444")
