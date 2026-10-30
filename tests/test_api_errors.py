"""Run from the project root: python -m unittest discover -s tests -v."""

import unittest
from unittest.mock import Mock, call, mock_open, patch

import requests

from api.client import KahootAPIError, get_json
from api.config import QUIZ_URL, REQUEST_TIMEOUT
from api.fetch import get_quiz_answers, parse_question
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
            result = get_quiz_answers("abc")
            self.assertEqual(result[0]["question"], "Q")
            self.assertEqual(result[0]["answers"], ["A", "C"])
            self.assertEqual(result[0]["status"], "supported")

    def test_quiz_identifier_is_quoted_as_one_url_path_segment(self):
        identifier = "abc/def?mode=all#section"
        with patch("api.fetch.get_json", return_value={"questions": []}) as get:
            self.assertEqual(get_quiz_answers(identifier), [])
        get.assert_called_once_with(f"{QUIZ_URL}abc%2Fdef%3Fmode%3Dall%23section")

    def test_invalid_quiz_identifiers_are_rejected_before_request(self):
        for identifier in (None, "", "  ", 123, ["abc"]):
            with self.subTest(identifier=identifier):
                with patch("api.fetch.get_json") as get:
                    with self.assertRaisesRegex(KahootAPIError, "Invalid quiz identifier"):
                        get_quiz_answers(identifier)
                get.assert_not_called()

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
        self.assertEqual(result[0]["question"], "Good")
        self.assertEqual(result[0]["answers"], ["A"])
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


class QuestionTypeTests(unittest.TestCase):
    def test_choice_types_extract_only_explicit_correct_answers(self):
        for kind in ("quiz", "true_false"):
            with self.subTest(kind=kind):
                item = parse_question({"type": kind, "question": "Q", "choices": [
                    {"answer": "True", "correct": True}, {"answer": "False", "correct": False}]})
                self.assertEqual(item["answers"], ["True"])
                self.assertEqual(item["status"], "supported")
                self.assertNotIn("warning", item)

    def test_opinion_types_do_not_extract_even_if_choices_claim_correctness(self):
        for kind in ("survey", "poll", "word_cloud", "brainstorm", "scale", "nps"):
            with self.subTest(kind=kind):
                item = parse_question({"type": kind, "question": "Your opinion?", "choices": [
                    {"answer": "A", "correct": True}]})
                self.assertEqual(item["answers"], [])
                self.assertEqual(item["status"], "no_answer_required")
                self.assertNotIn("warning", item)

    def test_slides_without_question_or_choices_are_not_corrupt(self):
        for kind in ("content", "slide"):
            with self.subTest(kind=kind):
                item = parse_question({"type": kind, "title": "Introduction"})
                self.assertEqual(item["question"], "Introduction")
                self.assertEqual(item["status"], "content")
                self.assertEqual(item["answers"], [])
                self.assertNotIn("warning", item)

    def test_special_and_unknown_types_never_guess_answers(self):
        for kind in ("jumble", "puzzle", "open_ended", "type_answer", "slider", "pin_it", "future_type"):
            with self.subTest(kind=kind):
                item = parse_question({"type": kind, "question": "Q", "choices": [
                    {"answer": "A", "correct": True}]})
                self.assertEqual(item["status"], "unsupported")
                self.assertEqual(item["type"], kind)
                self.assertEqual(item["answers"], [])
                self.assertNotIn("warning", item)

    def test_media_answers_do_not_return_partial_text_answers(self):
        item = parse_question({"type": "quiz", "question": "Q", "choices": [
            {"answer": "A", "correct": True}, {"image": "image-id", "correct": True}]})
        self.assertEqual(item["status"], "unsupported")
        self.assertEqual(item["answers"], [])
        self.assertIn("media", item["message"])

    def test_missing_and_invalid_type_are_distinct(self):
        question = {"question": "Q", "choices": [{"answer": "A", "correct": True}]}
        item = parse_question(question)
        self.assertEqual(item["type"], "unspecified")
        self.assertEqual(item["answers"], ["A"])
        for kind in (None, [], {}, 42, " "):
            with self.subTest(kind=kind):
                item = parse_question(dict(question, type=kind))
                self.assertEqual(item["status"], "invalid_data")
                self.assertEqual(item["answers"], [])
                self.assertIn("warning", item)

    def test_no_correct_flags_is_distinct_from_an_opinion_question(self):
        item = parse_question({"type": "quiz", "question": "Q", "choices": [
            {"answer": "A", "correct": False}]})
        self.assertEqual(item["status"], "no_correct_answer")
        self.assertEqual(item["answers"], [])

    def test_mixed_quiz_preserves_order_and_export_metadata(self):
        import json
        payload = {"questions": [{"type": "content"}, {"type": "poll", "question": "Opinion?"},
            {"type": "jumble", "question": "Order?"}, None,
            {"type": "quiz", "question": "Q", "choices": [{"answer": "A", "correct": True}]}]}
        with patch("api.fetch.get_json", return_value=payload), self.assertLogs("api.fetch", level="WARNING"):
            result = get_quiz_answers("abc")
        exported = json.loads(json.dumps(result))
        self.assertEqual([item["status"] for item in exported],
                         ["content", "no_answer_required", "unsupported", "invalid_data", "supported"])
        self.assertEqual(exported[-1]["answers"], ["A"])


class ControllerErrorTests(unittest.TestCase):
    def begin(self, controller, method="handle_search", value="abc"):
        with patch("core.controller.threading.Thread") as thread:
            getattr(controller, method)(value)
        return thread.call_args.kwargs["args"]

    def deliver(self, controller):
        controller.process_pending_results()

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
                    self.deliver(controller)
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
        self.deliver(controller)
        view.display_search_results.assert_called_once_with([])
        self.assertFalse(controller.is_busy)

    def test_new_fetch_clears_previous_export_data(self):
        controller = KahootController(Mock())
        controller.current_quiz_data = [{"question": "old"}]
        self.begin(controller, "handle_fetch")
        self.assertEqual(controller.current_quiz_data, [])

    def test_export_oserror_is_logged_and_reported(self):
        view = Mock()
        controller = KahootController(view)
        controller.current_quiz_data = [{"question": "Q", "answers": ["A"]}]
        with patch("builtins.open", side_effect=OSError("disk is full")):
            with self.assertLogs("core.controller", level="ERROR") as logs:
                controller.handle_export("quiz.json")
        self.assertIsNotNone(logs.records[0].exc_info)
        view.show_message.assert_called_once_with("Failed to export file.", "#EF4444")

    def test_export_serialization_error_is_logged_and_reported(self):
        view = Mock()
        controller = KahootController(view)
        controller.current_quiz_data = [{"not_json": object()}]
        with patch("builtins.open", mock_open()):
            with self.assertLogs("core.controller", level="ERROR") as logs:
                controller.handle_export("quiz.json")
        self.assertIsNotNone(logs.records[0].exc_info)
        view.show_message.assert_called_once_with("Failed to export file.", "#EF4444")


class EntryPointTests(unittest.TestCase):
    def test_interrupt_handler_accepts_keyboardinterrupt_subclasses(self):
        import sys
        original_hook = sys.excepthook
        try:
            from main import quiet_interrupt_handler

            class AppInterrupt(KeyboardInterrupt):
                pass

            with patch("main.sys.exit") as exit_process:
                quiet_interrupt_handler(AppInterrupt, AppInterrupt(), None)
            exit_process.assert_called_once_with(0)
        finally:
            sys.excepthook = original_hook


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
        self.controller.process_pending_results()
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


class ShutdownTests(unittest.TestCase):
    def test_queued_results_are_discarded_on_close(self):
        view = Mock()
        controller = KahootController(view)
        with patch("core.controller.threading.Thread"):
            controller.handle_fetch("abc")
        controller._publish_result(1, "fetch", [{"question": "old"}])
        view.reset_mock()
        controller.close()
        controller.close()
        controller.process_pending_results()
        self.assertEqual(view.mock_calls, [])
        self.assertFalse(controller.is_busy)
        self.assertEqual(controller.current_quiz_data, [])
        self.assertTrue(controller._results.empty())

    def test_late_worker_success_and_failure_never_touch_view(self):
        import threading
        for failure in (False, True):
            with self.subTest(failure=failure):
                view = Mock()
                controller = KahootController(view)
                started, release = threading.Event(), threading.Event()
                def fetch(_):
                    started.set()
                    if not release.wait(2):
                        raise RuntimeError("Test did not release worker")
                    if failure:
                        raise KahootAPIError("Late timeout")
                    return [{"question": "Late", "answers": ["A"]}]
                with patch("core.controller.get_quiz_answers", side_effect=fetch), patch("core.controller.logger"):
                    worker = threading.Thread(target=controller._fetch_worker, args=(1, "abc"))
                    worker.start()
                    try:
                        self.assertTrue(started.wait(2))
                        controller.close()
                    finally:
                        release.set()
                        worker.join(2)
                self.assertFalse(worker.is_alive())
                controller.process_pending_results()
                self.assertEqual(view.mock_calls, [])
                self.assertTrue(controller._results.empty())

    def test_actions_after_close_are_ignored(self):
        view = Mock()
        controller = KahootController(view)
        controller.close()
        with patch("core.controller.threading.Thread") as thread, patch("core.controller.pyperclip.copy") as copy:
            controller.handle_search("abc")
            controller.handle_fetch("abc")
            controller.handle_copy("A")
            controller.handle_export("unused.json")
            controller._finish_request(1, "error", "late")
            controller._publish_result(1, "fetch", [])
        thread.assert_not_called()
        copy.assert_not_called()
        self.assertEqual(view.mock_calls, [])

    def test_worker_results_only_render_when_main_thread_drains_queue(self):
        import threading
        owner = threading.get_ident()
        view = Mock()
        view.display_search_results.side_effect = lambda _: self.assertEqual(threading.get_ident(), owner)
        controller = KahootController(view)
        with patch("core.controller.threading.Thread"):
            controller.handle_search("abc")
        with patch("core.controller.search_quizzes", return_value=[]):
            worker = threading.Thread(target=controller._search_worker, args=(1, "abc"))
            worker.start()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        view.after.assert_not_called()
        view.display_search_results.assert_not_called()
        controller.process_pending_results()
        view.display_search_results.assert_called_once_with([])

    def fake_app(self):
        import threading
        import queue
        from types import SimpleNamespace
        app = SimpleNamespace(
            _closing=False, _hotkey_pending=threading.Event(), _poll_id="timer-1",
            _hotkey_handle="hotkey-1", _capture_hotkey_handle="hotkey-2",
            _capture_pending=threading.Event(), controller=Mock(), after_cancel=Mock(),
            after=Mock(return_value="timer-2"), destroy=Mock(),
            _poll_events=Mock(), _process_clipboard_search=Mock(),
            _start_screen_ocr=Mock(), _apply_ocr_result=Mock(),
            _ocr_results=queue.Queue(), _ocr_in_progress=False,
            _selection_overlay=None,
        )
        app.controller.is_busy = False
        return app

    def test_hotkey_callback_only_sets_event_and_ignores_close_and_busy(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        KahootParserApp._on_hotkey_press(app)
        self.assertTrue(app._hotkey_pending.is_set())
        app.after.assert_not_called()
        app._process_clipboard_search.assert_not_called()
        for closing, busy in ((True, False), (False, True)):
            app._closing, app.controller.is_busy = closing, busy
            app._hotkey_pending.clear()
            KahootParserApp._on_hotkey_press(app)
            self.assertFalse(app._hotkey_pending.is_set())

    def test_gui_close_cancels_timer_removes_own_hotkey_and_is_idempotent(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        with patch("gui.app.keyboard.remove_hotkey") as remove:
            KahootParserApp.on_closing(app)
            KahootParserApp.on_closing(app)
        app.controller.close.assert_called_once()
        app.after_cancel.assert_called_once_with("timer-1")
        self.assertEqual(remove.call_args_list, [call("hotkey-1"), call("hotkey-2")])
        app.destroy.assert_called_once()
        KahootParserApp._poll_events(app)
        app.after.assert_not_called()
        app.controller.process_pending_results.assert_not_called()

    def test_hotkey_cleanup_failure_does_not_prevent_window_destruction(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        with patch("gui.app.keyboard.remove_hotkey", side_effect=RuntimeError("hook failed")):
            with self.assertLogs("gui.app", level="ERROR"):
                KahootParserApp.on_closing(app)
        app.destroy.assert_called_once()

    def test_poll_handles_results_and_hotkey_on_gui_side(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        app._hotkey_pending.set()
        app._capture_pending.set()
        KahootParserApp._poll_events(app)
        app.controller.process_pending_results.assert_called_once()
        app._process_clipboard_search.assert_called_once()
        app._start_screen_ocr.assert_called_once()
        app._apply_ocr_result.assert_called_once()
        self.assertFalse(app._capture_pending.is_set())
        self.assertFalse(app._hotkey_pending.is_set())
        app.after.assert_called_once_with(50, app._poll_events)
        self.assertEqual(app._poll_id, "timer-2")


class ClipboardTests(unittest.TestCase):
    def fake_app(self):
        import threading
        import queue
        from types import SimpleNamespace
        controller = Mock()
        controller.is_busy = False
        return SimpleNamespace(
            _closing=False, controller=controller, _hotkey_handle=None,
            _capture_hotkey_handle=None, _capture_pending=threading.Event(),
            _ocr_results=queue.Queue(), _ocr_in_progress=False,
            _on_hotkey_press=Mock(), _on_capture_hotkey_press=Mock(),
            show_message=Mock(), search_entry=Mock(),
            deiconify=Mock(), attributes=Mock(), focus_force=Mock(), _on_search_clicked=Mock(),
            _open_selection_overlay=Mock(),
        )

    def test_hotkey_registration_failure_keeps_manual_search_available(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        with patch("gui.app.keyboard.add_hotkey", side_effect=OSError("denied")):
            with self.assertLogs("gui.app", level="ERROR"):
                KahootParserApp._register_hotkey(app)
        self.assertIsNone(app._hotkey_handle)
        self.assertIsNone(app._capture_hotkey_handle)
        app.show_message.assert_any_call(
            "F9 is unavailable. Enter a query and use Search instead.", "#D97706"
        )
        app.search_entry.get.return_value = "bike"
        KahootParserApp._on_search_clicked(app)
        app.controller.handle_search.assert_called_once_with("bike")

    def test_hotkey_registration_success_retains_cleanup_handle(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        with patch("gui.app.keyboard.add_hotkey", side_effect=["f9-handle", "f10-handle"]) as add:
            KahootParserApp._register_hotkey(app)
        self.assertEqual(app._hotkey_handle, "f9-handle")
        self.assertEqual(app._capture_hotkey_handle, "f10-handle")
        self.assertEqual(add.call_args_list, [
            call("F9", app._on_hotkey_press),
            call("F10", app._on_capture_hotkey_press),
        ])
        app.show_message.assert_not_called()

    def test_clipboard_read_failure_does_not_start_search_or_modify_entry(self):
        import pyperclip
        from gui.app import KahootParserApp
        app = self.fake_app()
        with patch("gui.app.pyperclip.paste", side_effect=pyperclip.PyperclipException("busy")):
            with self.assertLogs("gui.app", level="ERROR"):
                KahootParserApp._process_clipboard_search(app)
        app.search_entry.delete.assert_not_called()
        app._on_search_clicked.assert_not_called()
        self.assertIn("Could not read", app.show_message.call_args.args[0])

    def test_empty_and_non_text_clipboard_do_not_start_search(self):
        from gui.app import KahootParserApp
        for content in ("", "   ", None, b"bytes"):
            with self.subTest(content=content):
                app = self.fake_app()
                with patch("gui.app.pyperclip.paste", return_value=content):
                    KahootParserApp._process_clipboard_search(app)
                app.show_message.assert_called_once()
                app._on_search_clicked.assert_not_called()

    def test_clipboard_read_recovers_on_next_attempt(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        with patch("gui.app.pyperclip.paste", side_effect=[OSError("busy"), "  bike  "]):
            with self.assertLogs("gui.app", level="ERROR"):
                KahootParserApp._process_clipboard_search(app)
            KahootParserApp._process_clipboard_search(app)
        app.search_entry.insert.assert_called_once_with(0, "bike")
        app._on_search_clicked.assert_called_once()

    def test_capture_hotkey_only_schedules_work_on_gui_thread(self):
        import threading
        from types import SimpleNamespace
        from gui.app import KahootParserApp
        app = SimpleNamespace(
            _closing=False, controller=Mock(), _capture_pending=threading.Event(),
            _start_screen_ocr=Mock(), _ocr_in_progress=False,
        )
        app.controller.is_busy = False

        KahootParserApp._on_capture_hotkey_press(app)

        self.assertTrue(app._capture_pending.is_set())
        app._start_screen_ocr.assert_not_called()

    def test_capture_hotkey_ignores_closed_or_busy_app(self):
        import threading
        from types import SimpleNamespace
        from gui.app import KahootParserApp
        for closing, busy in ((True, False), (False, True)):
            app = SimpleNamespace(
                _closing=closing, controller=Mock(),
                _capture_pending=threading.Event(), _ocr_in_progress=False,
            )
            app.controller.is_busy = busy
            KahootParserApp._on_capture_hotkey_press(app)
            self.assertFalse(app._capture_pending.is_set())

    def test_f10_ocr_result_fills_search_without_starting_search(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        app._ocr_results.put(("What is 2 + 2?", None))
        KahootParserApp._apply_ocr_result(app)
        app.search_entry.delete.assert_called_once_with(0, "end")
        app.search_entry.insert.assert_called_once_with(0, "What is 2 + 2?")
        app.search_entry.focus_set.assert_called_once()
        app.controller.handle_search.assert_not_called()
        self.assertIn("Press Search", app.show_message.call_args.args[0])

    def test_f10_ocr_empty_result_does_not_change_search_or_search(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        app._ocr_results.put(("", None))
        KahootParserApp._apply_ocr_result(app)
        app.search_entry.delete.assert_not_called()
        app.controller.handle_search.assert_not_called()
        app.show_message.assert_called_once()

    def test_f10_ocr_failure_is_reported_without_search(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        app._ocr_in_progress = True
        app._ocr_results.put((None, "Tesseract OCR is not installed"))
        KahootParserApp._apply_ocr_result(app)
        self.assertFalse(app._ocr_in_progress)
        self.assertIn("Tesseract OCR is not installed", app.show_message.call_args.args[0])
        app.search_entry.delete.assert_not_called()
        app.controller.handle_search.assert_not_called()

    def test_f10_opens_region_selector_without_search(self):
        from gui.app import KahootParserApp
        app = self.fake_app()
        screenshot = Mock()
        with patch("gui.app.capture_primary_screen", return_value=screenshot) as capture:
            KahootParserApp._start_screen_ocr(app)
        self.assertTrue(app._ocr_in_progress)
        capture.assert_called_once_with()
        app._open_selection_overlay.assert_called_once_with()
        self.assertIs(app._screen_snapshot, screenshot)
        app.controller.handle_search.assert_not_called()

    def test_copy_failure_never_reports_success_and_can_retry(self):
        import pyperclip
        view = Mock()
        controller = KahootController(view)
        with patch("core.controller.pyperclip.copy", side_effect=[pyperclip.PyperclipException("busy"), None]):
            with self.assertLogs("core.controller", level="ERROR"):
                controller.handle_copy("A")
            self.assertIn("Could not copy", view.show_message.call_args.args[0])
            self.assertFalse(controller.is_busy)
            controller.handle_copy("A")
        self.assertIn("copied", view.show_message.call_args.args[0])


class TextFormattingTests(unittest.TestCase):
    def test_inline_html_and_entities(self):
        from api.text import clean_text
        self.assertEqual(clean_text('<p><b>Rock</b> &amp; Roll&nbsp;!</p>'), 'Rock & Roll !')
        self.assertEqual(clean_text('&lt;div&gt;'), '<div>')
        self.assertEqual(clean_text('&amp;lt;'), '&lt;')

    def test_paragraphs_breaks_and_whitespace(self):
        from api.text import clean_text
        self.assertEqual(clean_text('<p> First </p><p>Second<br>line</p>'), 'First\n\nSecond\nline')
        self.assertEqual(clean_text('  a\t b\r\nc  '), 'a b\nc')

    def test_math_code_and_indices_preserve_meaning(self):
        from api.text import clean_text
        self.assertEqual(clean_text('2 < 3 && 5 > 4'), '2 < 3 && 5 > 4')
        self.assertEqual(clean_text('x<sup>2</sup> + H<sub>2</sub>O'), 'x^(2) + H_(2)O')
        self.assertEqual(clean_text('Use &lt;b&gt;bold&lt;/b&gt;'), 'Use <b>bold</b>')
        self.assertEqual(clean_text('vector<int>'), 'vector<int>')

    def test_hidden_content_and_invalid_input(self):
        from api.text import clean_text
        self.assertEqual(clean_text('A<script>alert(1)</script><style>x</style>B'), 'AB')
        for value in (None, [], {}, 42):
            self.assertEqual(clean_text(value), '')

    def test_cleaning_is_used_by_search_and_quiz_parser(self):
        with patch('api.search.get_json', return_value={'entities': [{'uuid': 'abc', 'title': '<b>Bike</b> &amp; Parts'}]}):
            self.assertEqual(search_quizzes('abc')[0]['title'], 'Bike & Parts')
        item = parse_question({'type': 'quiz', 'question': '<p>What is <b>A</b>?</p>',
                              'choices': [{'correct': True, 'answer': '<b>A</b> &amp; B'}]})
        self.assertEqual(item['question'], 'What is A?')
        self.assertEqual(item['answers'], ['A & B'])

    def test_empty_formatted_answer_is_invalid_and_image_is_unsupported(self):
        for answer, status in [('<b> </b>', 'invalid_data'), ('<img src="x">', 'unsupported'),
                               ('Text <img src="x">', 'unsupported')]:
            with self.subTest(answer=answer):
                item = parse_question({'type': 'quiz', 'question': 'Q', 'choices': [{'correct': True, 'answer': answer}]})
                self.assertEqual(item['answers'], [])
                self.assertEqual(item['status'], status)

    def test_wrapping_tracks_width_and_display_scaling(self):
        from gui.app import KahootParserApp
        from types import SimpleNamespace
        label = Mock()
        label._get_widget_scaling.return_value = 1.5
        app = SimpleNamespace()
        with patch('gui.app.ctk.CTkLabel', return_value=label), patch('gui.app.Misc.bind') as bind:
            KahootParserApp._wrapped_label(app, Mock(), 'Long text', Mock())
        resize = bind.call_args.args[2]
        resize(SimpleNamespace(width=600))
        label.configure.assert_called_with(wraplength=396)
        count = label.configure.call_count
        resize(SimpleNamespace(width=600))
        self.assertEqual(label.configure.call_count, count)
        resize(SimpleNamespace(width=300))
        label.configure.assert_called_with(wraplength=196)


if __name__ == "__main__":
    unittest.main()

