import unittest
from unittest.mock import Mock, patch

import requests

from api.client import KahootAPIError, get_json
from api.config import REQUEST_TIMEOUT
from api.fetch import get_quiz_answers
from api.search import search_quizzes
from core.controller import KahootController


class APIErrorTests(unittest.TestCase):
    def response(self, payload=None, status=200):
        response = requests.Response()
        response.raw = Mock()
        response.status_code = status
        response.url = "https://example.test/quiz"
        response.json = Mock(return_value=payload)
        return response

    def test_success_preserves_timeout_and_parameters(self):
        with patch("api.client.requests.get", return_value=self.response({"ok": True})) as get:
            self.assertEqual(get_json("https://example.test", params={"query": "bike"}), {"ok": True})
        self.assertEqual(get.call_args.kwargs["timeout"], REQUEST_TIMEOUT)
        self.assertEqual(get.call_args.kwargs["params"], {"query": "bike"})

    def test_connection_and_timeout_errors_are_distinct(self):
        for error, message in [
            (requests.ConnectTimeout("connect"), "too long"),
            (requests.ReadTimeout("read"), "too long"),
            (requests.ConnectionError("offline"), "connect to Kahoot"),
            (requests.TooManyRedirects("redirect"), "request to Kahoot failed"),
        ]:
            with self.subTest(error=type(error).__name__):
                with patch("api.client.requests.get", side_effect=error):
                    with self.assertRaisesRegex(KahootAPIError, message) as caught:
                        get_json("https://example.test")
                self.assertIs(caught.exception.__cause__, error)

    def test_http_status_messages(self):
        for status, message in [
            (401, "authorization"), (403, "denied"), (404, "not found"),
            (429, "Too many requests"), (500, "server error"),
            (503, "server error"), (400, "HTTP 400"),
        ]:
            with self.subTest(status=status):
                with patch("api.client.requests.get", return_value=self.response(status=status)):
                    with self.assertRaisesRegex(KahootAPIError, message):
                        get_json("https://example.test")

    def test_invalid_json(self):
        response = self.response()
        response.json.side_effect = requests.exceptions.JSONDecodeError("invalid", "<html>", 0)
        with patch("api.client.requests.get", return_value=response):
            with self.assertRaisesRegex(KahootAPIError, "invalid JSON"):
                get_json("https://example.test")

    def test_empty_search_is_a_success(self):
        with patch("api.client.requests.get", return_value=self.response({"entities": []})):
            self.assertEqual(search_quizzes("nothing"), [])

    def test_successful_search_and_multiple_answers(self):
        with patch("api.client.requests.get", return_value=self.response(
            {"entities": [{"kahoot": {"uuid": "abc", "title": "Bike"}}]}
        )):
            self.assertEqual(search_quizzes("Bike"), [{"uuid": "abc", "title": "Bike"}])
        with patch("api.client.requests.get", return_value=self.response({"questions": [
            {"question": "Q", "choices": [
                {"answer": "A", "correct": True}, {"answer": "B", "correct": False},
                {"answer": "C", "correct": True},
            ]}
        ]})):
            self.assertEqual(get_quiz_answers("abc"), [{"question": "Q", "answers": ["A", "C"]}])

    def test_errors_propagate_from_both_api_functions(self):
        for function in (search_quizzes, get_quiz_answers):
            with self.subTest(function=function.__name__):
                with patch("api.client.requests.get", side_effect=requests.ReadTimeout):
                    with self.assertRaises(KahootAPIError):
                        function("abc")


class DataValidationTests(unittest.TestCase):
    def test_invalid_root_and_list_fields_raise_readable_errors(self):
        for function, target, key in [
            (search_quizzes, "api.search.get_json", "entities"),
            (get_quiz_answers, "api.fetch.get_json", "questions"),
        ]:
            for payload in (None, [], "text", 42, {}, {key: None}, {key: {}}, {key: "bad"}):
                with self.subTest(function=function.__name__, payload=payload):
                    with patch(target, return_value=payload):
                        with self.assertRaisesRegex(KahootAPIError, "format"):
                            function("abc")

    def test_empty_lists_are_successful(self):
        with patch("api.search.get_json", return_value={"entities": []}):
            self.assertEqual(search_quizzes("abc"), [])
        with patch("api.fetch.get_json", return_value={"questions": []}):
            self.assertEqual(get_quiz_answers("abc"), [])

    def test_mixed_search_results_keep_valid_records_and_fallback_shapes(self):
        payload = {"entities": [None, 42, {"uuid": []}, {"uuid": "   "},
            {"kahoot": None, "card": {"uuid": " a ", "title": None}},
            {"kahoot": {}, "card": {"uuid": "b", "title": "Bike"}},
            {"uuid": "c", "title": {"bad": "value"}},
        ]}
        with patch("api.search.get_json", return_value=payload), self.assertLogs("api.search", level="WARNING"):
            self.assertEqual(search_quizzes("abc"), [
                {"uuid": "a", "title": "Untitled"},
                {"uuid": "b", "title": "Bike"},
                {"uuid": "c", "title": "Untitled"},
            ])

    def test_all_invalid_search_results_are_not_reported_as_no_matches(self):
        with patch("api.search.get_json", return_value={"entities": [None, {}]}):
            with self.assertLogs("api.search", level="WARNING"):
                with self.assertRaisesRegex(KahootAPIError, "identifier"):
                    search_quizzes("abc")

    def test_broken_questions_preserve_positions_and_valid_neighbors(self):
        valid = {"question": "Good", "choices": [{"answer": "A", "correct": True}]}
        payload = {"questions": [valid, None, {"question": "Bad", "choices": None}, valid]}
        with patch("api.fetch.get_json", return_value=payload), self.assertLogs("api.fetch", level="WARNING"):
            result = get_quiz_answers("abc")
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], {"question": "Good", "answers": ["A"]})
        self.assertEqual(result[3], result[0])
        for index in (1, 2):
            self.assertEqual(result[index]["answers"], [])
            self.assertIn("warning", result[index])

    def test_invalid_choices_do_not_produce_partial_or_invented_answers(self):
        for bad in (None, [], "text", {}, {"correct": 1, "answer": "B"},
                    {"correct": "true", "answer": "B"}, {"correct": True, "answer": None},
                    {"correct": True, "answer": ["B"]}, {"correct": True, "answer": " "}):
            with self.subTest(choice=bad):
                payload = {"questions": [{"question": "Q", "choices": [
                    {"correct": True, "answer": "A"}, bad]}]}
                with patch("api.fetch.get_json", return_value=payload), self.assertLogs("api.fetch", level="WARNING"):
                    result = get_quiz_answers("abc")
                self.assertEqual(result[0]["answers"], [])
                self.assertIn("warning", result[0])

    def test_non_list_choices_and_non_string_questions_are_safe(self):
        for choices in (None, {}, "text", 4):
            with self.subTest(choices=choices):
                with patch("api.fetch.get_json", return_value={"questions": [{"question": [], "choices": choices}]}):
                    with self.assertLogs("api.fetch", level="WARNING"):
                        result = get_quiz_answers("abc")
                self.assertIsInstance(result[0]["question"], str)
                self.assertEqual(result[0]["answers"], [])
                self.assertIn("warning", result[0])

    def test_warnings_survive_json_export(self):
        import json
        import tempfile
        from pathlib import Path
        view = Mock()
        controller = KahootController(view)
        with patch("api.fetch.get_json", return_value={"questions": [None]}):
            with self.assertLogs("api.fetch", level="WARNING"):
                controller.current_quiz_data = get_quiz_answers("abc")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quiz.json"
            controller.handle_export(path)
            exported = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("warning", exported[0])
        self.assertEqual(exported[0]["answers"], [])


class ControllerErrorTests(unittest.TestCase):
    def begin(self, controller, method="handle_search", value="abc"):
        with patch("core.controller.threading.Thread") as thread:
            getattr(controller, method)(value)
        return thread.call_args.kwargs["args"]

    def deliver(self, view):
        _, callback, *args = view.after.call_args.args
        callback(*args)

    def test_worker_errors_schedule_message_and_log_traceback(self):
        for entry, worker, dependency in [
            ("handle_search", "_search_worker", "search_quizzes"),
            ("handle_fetch", "_fetch_worker", "get_quiz_answers"),
        ]:
            for error in (KahootAPIError("Request timed out."), ValueError("broken parser")):
                with self.subTest(worker=worker, error=type(error).__name__):
                    view = Mock()
                    controller = KahootController(view)
                    args = self.begin(controller, entry)
                    with patch("core.controller." + dependency, side_effect=error):
                        with self.assertLogs("core.controller", level="ERROR") as logs:
                            getattr(controller, worker)(*args)
                    self.assertTrue(controller.is_busy)
                    view.show_message.assert_not_called()
                    self.deliver(view)
                    self.assertFalse(controller.is_busy)
                    message, color = view.show_message.call_args.args
                    self.assertEqual(color, "#EF4444")
                    self.assertIn("Request timed out" if isinstance(error, KahootAPIError) else "Unexpected error", message)
                    self.assertIsNotNone(logs.records[0].exc_info)
                    view.display_search_results.assert_not_called()
                    view.display_quiz_answers.assert_not_called()

    def test_empty_search_uses_result_callback(self):
        view = Mock()
        controller = KahootController(view)
        args = self.begin(controller)
        with patch("core.controller.search_quizzes", return_value=[]):
            controller._search_worker(*args)
        self.deliver(view)
        view.display_search_results.assert_called_once_with([])
        self.assertFalse(controller.is_busy)

    def test_new_fetch_clears_previous_export_data(self):
        controller = KahootController(Mock())
        controller.current_quiz_data = [{"question": "old"}]
        self.begin(controller, "handle_fetch")
        self.assertEqual(controller.current_quiz_data, [])


class ControllerRequestTests(unittest.TestCase):
    def setUp(self):
        self.view = Mock()
        self.controller = KahootController(self.view)
        self.thread_patch = patch("core.controller.threading.Thread")
        self.thread = self.thread_patch.start()
        self.addCleanup(self.thread_patch.stop)

    def test_repeated_search_and_fetch_start_only_one_worker(self):
        for first in ("handle_search", "handle_fetch"):
            with self.subTest(first=first):
                self.thread.reset_mock()
                controller = KahootController(Mock())
                getattr(controller, first)("first")
                for _ in range(10):
                    controller.handle_search("second")
                    controller.handle_search("   ")
                    controller.handle_fetch("other")
                self.thread.assert_called_once()
                controller.view.show_loading.assert_called_once()
                controller.view.show_message.assert_not_called()

    def test_busy_is_set_before_view_receives_loading(self):
        def reenter(_):
            self.assertTrue(self.controller.is_busy)
            self.controller.handle_search("reentrant")
        self.view.show_loading.side_effect = reenter
        self.controller.handle_search("first")
        self.thread.assert_called_once()

    def test_completion_waits_for_gui_callback(self):
        self.controller.handle_fetch("quiz")
        args = self.thread.call_args.kwargs["args"]
        data = [{"question": "new", "answers": ["A"]}]
        with patch("core.controller.get_quiz_answers", return_value=data):
            self.controller._fetch_worker(*args)
        self.assertTrue(self.controller.is_busy)
        self.assertEqual(self.controller.current_quiz_data, [])
        self.controller.handle_search("blocked")
        self.thread.assert_called_once()
        _, callback, *result_args = self.view.after.call_args.args
        callback(*result_args)
        self.assertFalse(self.controller.is_busy)
        self.assertEqual(self.controller.current_quiz_data, data)
        self.view.display_quiz_answers.assert_called_once_with(data)
        self.controller.handle_search("next")
        self.assertEqual(self.thread.call_count, 2)

    def test_old_callbacks_cannot_unlock_or_overwrite_new_request(self):
        self.controller.handle_search("first")
        first_id = self.thread.call_args.kwargs["args"][0]
        self.controller._finish_request(first_id, "search", [])
        self.controller.handle_fetch("second")
        second_id = self.thread.call_args.kwargs["args"][0]
        self.view.reset_mock()
        for kind, result in [("search", []), ("fetch", [{"question": "old"}]), ("error", "old error")]:
            self.controller._finish_request(first_id, kind, result)
        self.assertTrue(self.controller.is_busy)
        self.assertEqual(self.controller.current_quiz_data, [])
        self.view.assert_has_calls([])
        self.assertEqual(self.view.mock_calls, [])
        self.controller._finish_request(second_id, "fetch", [])
        self.assertFalse(self.controller.is_busy)

    def test_duplicate_completion_is_ignored(self):
        self.controller.handle_search("first")
        request_id = self.thread.call_args.kwargs["args"][0]
        self.controller._finish_request(request_id, "search", [])
        self.controller._finish_request(request_id, "search", [])
        self.view.display_search_results.assert_called_once_with([])

    def test_thread_start_failure_releases_busy_state(self):
        self.thread.return_value.start.side_effect = RuntimeError("cannot start thread")
        with self.assertLogs("core.controller", level="ERROR"):
            self.controller.handle_search("first")
        self.assertFalse(self.controller.is_busy)
        self.view.show_message.assert_called_once()
        self.thread.return_value.start.side_effect = None
        self.controller.handle_search("retry")
        self.assertTrue(self.controller.is_busy)

    def test_empty_query_does_not_start_worker(self):
        self.controller.handle_search("   ")
        self.thread.assert_not_called()
        self.assertFalse(self.controller.is_busy)
        self.view.show_message.assert_called_once()

    def test_copy_and_export_do_not_interfere_with_loading(self):
        self.controller.handle_search("first")
        self.controller.current_quiz_data = [{"question": "old"}]
        with patch("core.controller.pyperclip.copy") as copy, patch("builtins.open") as opened:
            self.controller.handle_copy("old answer")
            self.controller.handle_export("unused.json")
        copy.assert_not_called()
        opened.assert_not_called()
        self.view.show_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
