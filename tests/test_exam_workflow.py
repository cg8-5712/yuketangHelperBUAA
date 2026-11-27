"""Exam workflow: answering, saving, and submit gating."""

import unittest

from yuketang_helper.platform.client import PlatformError
from yuketang_helper.platform.exam import ExamAuthError
from yuketang_helper.workflows.exam import examHelper


def choice(problem_id, result=None, problem_type=1,
           options=(("A", "a"), ("B", "b"))):
    return {
        "problem_id": problem_id,
        "ProblemType": problem_type,
        "Body": "<p>question</p>",
        "Options": [{"key": key, "value": value} for key, value in options],
        "result": [] if result is None else result,
    }


def judgement(problem_id, result=None):
    return choice(problem_id, result=result, problem_type=6,
                  options=(("true", "正确"), ("false", "错误")))


class StubCourses:
    def leaves(self, classroom_id, course_sign, leaf_type):
        return [{"id": 91, "name": "期末考试", "progress": {"status": "进行中"}}]

    def leaf_info(self, classroom_id, leaf_id):
        return {"content_info": {"exam_id": 2148705}}


class StubExam:
    def __init__(self, paper, fail_on=(), status=1, saved_results=()):
        self.paper_data = paper
        self.fail_on = set(fail_on)
        self.status = status
        self.saved_results = list(saved_results)
        self.saved = []
        self.submitted = []
        self.started = 0

    def cover(self, exam_id):
        return {"result": {"status": self.status}}

    def entry_info(self, exam_id):
        return {"status": self.status}

    def problem_results(self, exam_id):
        return {"problem_results": [
            {"problem_id": problem_id, "result": result, "finished": True}
            for problem_id, result in self.saved_results
        ]}

    def paper(self, exam_id):
        return self.paper_data

    def start(self, exam_id):
        self.started += 1
        return {}

    def save_answers(self, exam_id, results, record=None):
        problem_id = results[-1]["problem_id"]
        if problem_id in self.fail_on:
            raise PlatformError("save rejected")
        self.saved.append(results[-1])
        return {}

    def submit(self, exam_id, results):
        self.submitted.append(results)
        return {}


class StubBank:
    def lookup(self, question):
        return None

    def invalidate(self, question):
        pass


class StubAI:
    def get_answer(self, problem, problem_type="Choice"):
        return {"Judgement": "true", "MultipleChoice": "A,B"}.get(problem_type, "A")


def build(paper, fail_on=(), status=1, saved_results=()):
    helper = examHelper.__new__(examHelper)
    helper.courses = StubCourses()
    helper.exam = StubExam(paper, fail_on, status=status,
                          saved_results=saved_results)
    helper.bank = StubBank()
    helper.ai = StubAI()
    helper.stop_event = None
    helper.auto_start = False
    helper.decrypt = None
    helper.access_token = "token"
    helper.user_id = 64024722
    helper._read_paper = lambda exam_id: helper.exam.paper_data
    return helper


class ExamWorkflowTests(unittest.TestCase):
    def test_display_letters_map_to_platform_keys(self):
        paper = {"problems": [
            choice(9, result="k2", options=(("k1", "a"), ("k2", "b"))),
            choice(1, options=(("k1", "a"), ("k2", "b"))),
            choice(2, problem_type=2, options=(("k1", "a"), ("k2", "b"))),
        ]}
        helper = build(paper)
        self.assertTrue(helper.do_exam(1, "sign", "course"))
        submitted = {item["problem_id"]: item["result"]
                     for item in helper.exam.submitted[0]}
        self.assertEqual(submitted[1], "k1")
        self.assertEqual(submitted[2], ["k1", "k2"])

    def test_answers_unanswered_problems_and_submits(self):
        paper = {"problems": [choice(1), choice(2, result="B")]}
        helper = build(paper)
        self.assertTrue(helper.do_exam(1, "sign", "course"))
        self.assertEqual([item["problem_id"] for item in helper.exam.saved], [1])
        submitted = {item["problem_id"]: item["result"]
                     for item in helper.exam.submitted[0]}
        self.assertEqual(submitted[1], "A")
        self.assertEqual(submitted[2], "B")

    def test_save_failure_skips_submit(self):
        paper = {"problems": [choice(1)]}
        helper = build(paper, fail_on={1})
        self.assertFalse(helper.do_exam(1, "sign", "course"))
        self.assertEqual(helper.exam.submitted, [])

    def test_multiple_choice_and_judgement_results(self):
        paper = {"problems": [choice(3, result="B"),
                              choice(1, problem_type=2),
                              judgement(2)]}
        helper = build(paper)
        self.assertTrue(helper.do_exam(1, "sign", "course"))
        submitted = {item["problem_id"]: item["result"]
                     for item in helper.exam.submitted[0]}
        self.assertEqual(submitted[1], ["A", "B"])
        self.assertEqual(submitted[2], "true")
        self.assertEqual(submitted[3], "B")

    def test_unstarted_exam_is_not_started_by_default(self):
        paper = {"problems": [choice(1)]}
        helper = build(paper, status=0)
        self.assertFalse(helper.do_exam(1, "sign", "course"))
        self.assertEqual(helper.exam.saved, [])
        self.assertEqual(helper.exam.started, 0)

    def test_submitted_exam_is_skipped(self):
        paper = {"problems": [choice(1)]}
        helper = build(paper, status=5)
        self.assertTrue(helper.do_exam(1, "sign", "course"))
        self.assertEqual(helper.exam.saved, [])
        self.assertEqual(helper.exam.submitted, [])

    def test_missing_token_is_reported(self):
        paper = {"problems": [choice(1)]}
        helper = build(paper)

        def reject(exam_id):
            raise ExamAuthError("考试身份认证已失效")

        def fail_refresh(exam_id):
            raise ExamAuthError("考试身份认证已失效")

        helper.exam.entry_info = reject
        helper.exam.refresh = fail_refresh
        self.assertIn("身份认证", helper.check_token(2148705))

    def test_stale_token_is_refreshed_once(self):
        paper = {"problems": [choice(1, result="B")]}
        helper = build(paper)
        calls = {"refresh": 0}

        def stale(exam_id):
            raise ExamAuthError("考试身份认证已失效")

        def refresh(exam_id):
            calls["refresh"] += 1
            return "fresh"

        stale_once = {"done": False}

        def cover(exam_id):
            if not stale_once["done"]:
                stale_once["done"] = True
                raise ExamAuthError("考试身份认证已失效")
            return {"result": {"status": 1}}

        helper.exam.cover = cover
        helper.exam.refresh = refresh
        self.assertTrue(helper.do_exam(1, "sign", "course"))
        self.assertEqual(calls["refresh"], 1)

    def test_valid_token_reports_no_error(self):
        helper = build({"problems": [choice(1)]})
        helper.exam.entry_info = lambda exam_id: {"status": 1}
        self.assertIsNone(helper.check_token(2148705))

    def test_auto_start_restarts_unstarted_exam(self):
        paper = {"problems": [choice(1)]}
        helper = build(paper, status=0)
        helper.auto_start = True
        self.assertTrue(helper.do_exam(1, "sign", "course"))
        self.assertEqual(helper.exam.started, 1)
        self.assertEqual(helper.exam.submitted[0][0]["result"], "A")

    def test_saved_answers_are_reused(self):
        paper = {"problems": [choice(1), choice(2)]}
        helper = build(paper, saved_results=((2, "B"),))
        self.assertTrue(helper.do_exam(1, "sign", "course"))
        submitted = {item["problem_id"]: item["result"]
                     for item in helper.exam.submitted[0]}
        self.assertEqual(submitted[2], "B")
        self.assertEqual([item["problem_id"] for item in helper.exam.saved], [1])


if __name__ == "__main__":
    unittest.main()