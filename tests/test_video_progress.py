"""Regression checks for progress queries, without sending video heartbeats."""

import threading
import unittest
from unittest.mock import Mock

from yuketang_helper.platform.client import PlatformError
from yuketang_helper.platform.video import VideoAPI


class VideoProgressTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(university_id="3832")
        self.api = VideoAPI(self.client)

    def query(self, response):
        self.client.get_json.return_value = response
        return self.api.progress(3447587, 123, 26845551, 49516999)

    def test_successful_empty_records_start_at_zero(self):
        self.assertEqual(
            self.query({"message": None, "code": 0, "data": {}}),
            {"completed": 0, "rate": 0, "watch_length": 0},
        )

    def test_existing_progress_is_preserved(self):
        for record in (
            {"completed": 0, "rate": 0.42, "watch_length": 123},
            {"completed": 1, "rate": 1, "watch_length": 456},
        ):
            with self.subTest(record=record):
                self.assertIs(
                    self.query({"code": 0, "data": {"49516999": record}}), record
                )

    def test_api_error_reports_code_and_message(self):
        with self.assertRaisesRegex(PlatformError, "code=401.*login required"):
            self.query({"code": 401, "message": "login required", "data": {}})

    def test_api_error_with_msg_is_not_hidden_by_existing_record(self):
        with self.assertRaisesRegex(PlatformError, "permission denied"):
            self.query({"code": 403, "msg": "permission denied",
                        "data": {"49516999": {"rate": 1}}})

    def test_malformed_responses_are_not_zero_progress(self):
        for response in (
            None, [], "invalid", {}, {"data": {}}, {"code": 0},
            {"code": 0, "data": None}, {"code": 0, "data": []},
            {"code": 0, "data": {"other_video": {"rate": 1}}},
            {"code": 0, "data": {"49516999": None}},
            {"code": 0, "data": {"49516999": []}},
        ):
            with self.subTest(response=response):
                with self.assertRaises(PlatformError):
                    self.query(response)

    def test_request_preserves_parameters_and_stop_event(self):
        stop_event = threading.Event()
        self.client.get_json.return_value = {"code": 0, "data": {}}
        self.api.progress(3447587, 123, 26845551, "49516999", stop_event)
        self.client.get_json.assert_called_once_with(
            "/video-log/get_video_watch_progress/?cid=3447587&user_id=123"
            "&classroom_id=26845551&video_type=video&vtype=rate"
            "&video_id=49516999&snapshot=1&term=latest&uv_id=3832",
            stop_event=stop_event,
        )

    def test_transport_error_is_preserved(self):
        self.client.get_json.side_effect = PlatformError("HTTP 503")
        with self.assertRaisesRegex(PlatformError, "HTTP 503"):
            self.api.progress(3447587, 123, 26845551, 49516999)


if __name__ == "__main__":
    unittest.main()
