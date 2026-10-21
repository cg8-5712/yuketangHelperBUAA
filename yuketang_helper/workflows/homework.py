"""Exercise workflow: read, answer, submit, and verify."""

import json
import random
import time

from ..answers.ai import OpenAI_ask
from ..answers.bank import QuestionBank
from ..answers.parser import parse_answer
from ..decryption.font import Decrypt_problem
from ..logging import log, wait_for_platform
from ..models import SubmitStatus
from ..platform.client import PlatformClient, PlatformError
from ..platform.courses import CourseAPI
from ..platform.exercise import ExerciseAPI
from .discussion import DiscussionWorkflow


class homeworkHelper:
    def __init__(self, domain, cookies, user_id, university_id, header,
                 api_mode="chat_completions", client=None, ai=None, bank=None,
                 stop_event=None, run_discussions=True):
        self.client = client or PlatformClient(domain, university_id, header)
        self.courses = CourseAPI(self.client)
        self.exercises = ExerciseAPI(self.client)
        self.ai = ai or OpenAI_ask(api_mode=api_mode)
        self.bank = bank or QuestionBank()
        self.decrypt = Decrypt_problem(header)
        self.discussions = DiscussionWorkflow(self.courses, self.client, self.ai)
        self.stop_event = stop_event
        self.run_discussions = run_discussions

    def _stopped(self):
        return self.stop_event is not None and self.stop_event.is_set()

    def _read_problems(self, classroom_id, leaf_id):
        info = self.courses.leaf_info(classroom_id, leaf_id)
        try:
            exercise_id = info["content_info"]["leaf_type_id"]
        except (KeyError, TypeError) as exc:
            raise PlatformError(f"作业 {leaf_id} 缺少 leaf_type_id") from exc
        raw = self.exercises.list(exercise_id)
        font = raw.get("data", {}).get("font")
        if font:
            raw = json.loads(self.decrypt.get_encrypt_string(
                json.dumps(raw, ensure_ascii=False), font
            ))
        try:
            return exercise_id, raw["data"]["name"], raw["data"]["problems"]
        except (KeyError, TypeError) as exc:
            raise PlatformError(f"作业 {leaf_id} 题目响应格式错误") from exc

    @staticmethod
    def _question(problem):
        content = problem["content"]
        question = {"Type": content["Type"], "Body": content["Body"]}
        if content["Type"] != "FillBlank":
            question["Options"] = [
                f"{option['key']}. {option['value']}"
                for option in content.get("Options", [])
            ]
        return question

    def _answer(self, question):
        cached = self.bank.lookup(question)
        if cached is not None:
            try:
                answer = parse_answer(question, cached[0])
                log("题库命中，跳过 AI 请求")
                if cached[1]:
                    log(f"题库解析：{cached[1]}")
                return answer, True
            except (ValueError, TypeError):
                self.bank.invalidate(question)
                log("题库答案格式无效，已禁用", level="Warning")
        raw_answer = self.ai.get_answer(
            json.dumps(question, ensure_ascii=False), problem_type=question["Type"]
        )
        return parse_answer(question, raw_answer), False

    def _submission_count(self, exercise_id, problem_id):
        """Read submission count after an ambiguous POST timeout."""
        fresh = self.exercises.list(exercise_id)
        for problem in fresh.get("data", {}).get("problems", []):
            if str(problem.get("problem_id")) == str(problem_id):
                return problem.get("user", {}).get("my_count")
        raise PlatformError(f"无法确认题目 {problem_id} 的提交状态")

    def _submit(self, classroom_id, exercise_id, problem, question, answer, from_bank):
        problem_id = problem["problem_id"]
        initial_count = problem.get("user", {}).get("my_count", 0)
        for attempt in range(1, 4):
            if self._stopped():
                return False
            delay = random.uniform(0.3, 1.0)
            if self.stop_event is not None:
                if self.stop_event.wait(delay):
                    return False
            else:
                time.sleep(delay)
            try:
                result = self.exercises.submit(
                    classroom_id, problem_id, answer,
                    fill_blank=question["Type"] == "FillBlank",
                )
            except PlatformError as exc:
                try:
                    current_count = self._submission_count(exercise_id, problem_id)
                except PlatformError:
                    log(f"题目 {problem_id} 提交状态不明：{exc}；停止重试", level="Error")
                    return False
                if current_count is None or current_count > initial_count:
                    log(f"题目 {problem_id} 可能已提交，需人工确认；停止重试", level="Warning")
                    return False
                if attempt == 3:
                    log(f"题目 {problem_id} 请求失败：{exc}", level="Error")
                    return False
                delay = min(2 ** attempt, 8) + random.uniform(0, 1)
                if self.stop_event is not None:
                    if self.stop_event.wait(delay):
                        return False
                else:
                    time.sleep(delay)
                continue
            if result.status == SubmitStatus.RATE_LIMITED:
                if attempt == 3:
                    log(f"题目 {problem_id} 限流次数已达上限", level="Error")
                    return False
                if not wait_for_platform(result.retry_after or 1, self.stop_event):
                    return False
                continue
            if result.status == SubmitStatus.CORRECT:
                self.bank.save_verified(question, answer, result.explanation)
                log(f"题目 {problem_id} 回答正确，得分：{result.score}")
                if result.explanation and not from_bank:
                    log(f"解析：{result.explanation}")
                return True
            if result.status == SubmitStatus.INCORRECT:
                if from_bank:
                    self.bank.invalidate(question)
                    log(f"题目 {problem_id} 题库答案判错，已禁用", level="Warning")
                else:
                    log(f"题目 {problem_id} 回答错误，得分：{result.score}", level="Warning")
                return False
            log(f"题目 {problem_id} 提交失败：{result.message}", level="Error")
            return False
        return False

    def do_homework(self, classroom_id, course_sign, course_name):
        leaves = self.courses.leaves(classroom_id, course_sign, 6)
        log(f"{course_name} 共有 {len(leaves)} 个作业")
        all_confirmed = True
        for leaf in leaves:
            if self._stopped():
                return False
            leaf_id = leaf["id"]
            exercise_id, title, problems = self._read_problems(classroom_id, leaf_id)
            leaf_confirmed = True
            for problem in problems:
                if self._stopped():
                    return False
                problem_id = problem["problem_id"]
                user = problem.get("user", {})
                if user.get("my_count", 0) >= user.get("count", 1):
                    log(f"题目 {problem_id} 已达到作答上限，跳过")
                    if user.get("is_right") is not True:
                        leaf_confirmed = False
                    continue
                question = self._question(problem)
                log(f"题目 {problem_id}：{json.dumps(question, ensure_ascii=False)}")
                try:
                    answer, from_bank = self._answer(question)
                except (ValueError, TypeError) as exc:
                    log(f"题目 {problem_id} 答案无效：{exc}", level="Error")
                    leaf_confirmed = False
                    continue
                log(f"答案：{answer}")
                if not self._submit(classroom_id, exercise_id, problem, question, answer, from_bank):
                    leaf_confirmed = False
            if leaf_confirmed:
                log(f"{title} 习题已完成")
            else:
                log(f"{title} 存在未完成题目", level="Warning")
                all_confirmed = False
        discussions_complete = (
            self.discussions.run(classroom_id, course_sign)
            if self.run_discussions and not self._stopped() else not self._stopped()
        )
        return all_confirmed and discussions_complete
