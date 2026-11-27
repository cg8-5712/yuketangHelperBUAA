"""Completion rules for the exercise workflow."""

import unittest

from yuketang_helper.models import SubmitStatus
from yuketang_helper.workflows.homework import homeworkHelper


class StubCourses:
    def leaves(self, classroom_id, course_sign, leaf_type):
        return [{"id": 1, "name": "10.3 习题"}]


def problem(problem_id, answered=0, allowed=1, is_right=None):
    return {
        "problem_id": problem_id,
        "user": {"my_count": answered, "count": allowed, "is_right": is_right},
        "content": {
            "Type": "SingleChoice",
            "Body": "<p>question</p>",
            "Options": [{"key": "A", "value": "a"}],
        },
    }


class HomeworkCompletionTests(unittest.TestCase):
    def build(self, problems, statuses):
        helper = homeworkHelper.__new__(homeworkHelper)
        helper.courses = StubCourses()
        helper.stop_event = None
        helper.run_discussions = False
        helper._read_problems = lambda classroom_id, leaf_id: (1, "10.3 习题", problems)
        helper._answer = lambda question: (["A"], False)
        helper._submit = lambda classroom_id, exercise_id, item, question, answer, from_bank: statuses.pop(0)
        return helper

    def test_incorrect_answers_that_used_all_attempts_are_not_unfinished(self):
        problems = [
            problem(1, answered=1, is_right=True),
            problem(2, answered=1, is_right=False),
            problem(3),
        ]
        helper = self.build(problems, [(SubmitStatus.INCORRECT, "")])
        self.assertTrue(helper.do_homework(1, "sign", "course"))

    def test_unsubmitted_and_unknown_answers_keep_exercise_unfinished(self):
        problems = [problem(1), problem(2), problem(3)]
        statuses = [(SubmitStatus.FAILED, "请求失败"),
                    (SubmitStatus.UNKNOWN, "提交状态不明"),
                    (SubmitStatus.CORRECT, "")]
        helper = self.build(problems, statuses)
        self.assertFalse(helper.do_homework(1, "sign", "course"))

    def test_rate_limited_after_retries_is_unfinished(self):
        helper = self.build([problem(1)], [(SubmitStatus.RATE_LIMITED, "限流次数已达上限")])
        self.assertFalse(helper.do_homework(1, "sign", "course"))


if __name__ == "__main__":
    unittest.main()