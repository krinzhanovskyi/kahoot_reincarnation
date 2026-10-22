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


class ControllerErrorTests(unittest.TestCase):
    def test_worker_errors_schedule_message_and_log_traceback(self):
        for method, dependency in [("_search_worker", "search_quizzes"), ("_fetch_worker", "get_quiz_answers")]:
            for error in (KahootAPIError("Request timed out."), ValueError("broken parser")):
                with self.subTest(method=method, error=type(error).__name__):
                    view = Mock()
                    controller = KahootController(view)
                    with patch("core.controller." + dependency, side_effect=error):
                        with self.assertLogs("core.controller", level="ERROR") as logs:
                            getattr(controller, method)("abc")
                    args = view.after.call_args.args
                    self.assertEqual(args[:2], (0, view.show_message))
                    self.assertEqual(args[3], "#EF4444")
                    self.assertIn("Request timed out" if isinstance(error, KahootAPIError) else "Unexpected error", args[2])
                    self.assertIsNotNone(logs.records[0].exc_info)
                    view.display_search_results.assert_not_called()
                    view.display_quiz_answers.assert_not_called()

    def test_empty_search_uses_result_callback(self):
        view = Mock()
        with patch("core.controller.search_quizzes", return_value=[]):
            KahootController(view)._search_worker("abc")
        view.after.assert_called_once_with(0, view.display_search_results, [])

    def test_new_fetch_clears_previous_export_data(self):
        controller = KahootController(Mock())
        controller.current_quiz_data = [{"question": "old"}]
        with patch("core.controller.threading.Thread"):
            controller.handle_fetch("new")
        self.assertEqual(controller.current_quiz_data, [])


if __name__ == "__main__":
    unittest.main()
