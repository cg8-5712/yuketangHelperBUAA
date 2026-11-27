"""Exam workflow: read a paper, answer it, save answers, then submit."""

import json
import random
import time

from ..answers.ai import OpenAI_ask
from ..answers.bank import QuestionBank
from ..answers.parser import parse_answer
from ..decryption.font import Decrypt_problem
from ..logging import log
from ..platform.client import PlatformClient, PlatformError
from ..platform.courses import CourseAPI
from ..platform.exam import (
    STATUS_IN_PROGRESS, STATUS_NOT_STARTED, ExamAPI, ExamAuthError,
)


EXAM_LEAF_TYPE = 5

TYPE_BY_PROBLEM_TYPE = {
    1: "SingleChoice",
    2: "MultipleChoice",
    3: "Polling",
    4: "FillBlank",
    5: "ShortAnswer",
    6: "Judgement",
    9: "Programming",
}

SUPPORTED_TYPES = {
    "SingleChoice", "MultipleChoice", "Judgement",
    "FillBlank", "ShortAnswer", "Polling",
}


def _format_ids(problem_ids):
    return "、".join(str(problem_id) for problem_id in problem_ids)


def _letter(index):
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _letter_index(letter):
    value = 0
    for char in str(letter).strip().upper():
        if not "A" <= char <= "Z":
            raise ValueError(f"无法识别的选项：{letter}")
        value = value * 26 + (ord(char) - ord("A") + 1)
    if not value:
        raise ValueError(f"无法识别的选项：{letter}")
    return value - 1


class examHelper:
    def __init__(self, domain, cookies, user_id, university_id, header,
                 api_mode="chat_completions", client=None, ai=None, bank=None,
                 stop_event=None, auto_start=False, access_token=None):
        self.client = client or PlatformClient(domain, university_id, header)
        self.courses = CourseAPI(self.client)
        self.user_id = user_id
        self.access_token = access_token
        self.exam = ExamAPI(self.client, token=access_token)
        self.ai = ai or OpenAI_ask(api_mode=api_mode)
        self.bank = bank or QuestionBank()
        self.decrypt = Decrypt_problem(header)
        self.stop_event = stop_event
        self.auto_start = auto_start

    def _stopped(self):
        return self.stop_event is not None and self.stop_event.is_set()

    def _pause(self, seconds):
        if self.stop_event is not None:
            return not self.stop_event.wait(seconds)
        time.sleep(seconds)
        return True

    def leaves(self, classroom_id, course_sign):
        return self.courses.leaves(classroom_id, course_sign, EXAM_LEAF_TYPE)

    def _exam_id(self, classroom_id, leaf_id):
        info = self.courses.leaf_info(classroom_id, leaf_id)
        content = (info or {}).get("content_info") or {}
        for key in ("leaf_type_id", "exam_id", "source_id"):
            value = content.get(key) or (info or {}).get(key)
            if value:
                return value
        keys = sorted(content) or sorted((info or {}))
        raise PlatformError(f"考试 {leaf_id} 缺少 exam_id（可用字段：{keys}）")

    def set_access_token(self, token):
        """Switch to a fresh exam-host session using the given x_access_token."""
        self.access_token = token
        self.exam.set_token(token)

    def needs_token(self):
        return not self.access_token

    def _authorize(self, exam_id):
        """Ask the main site for a one-time crypt and trade it for a token."""
        token = self.exam.refresh(exam_id)
        self.access_token = token
        log("已自动获取考试端凭证", level="Info")
        return token

    def _call(self, exam_id, action, *args, **kwargs):
        """Run an exam-room call, refreshing the token once on a 401."""
        if self.access_token:
            try:
                return getattr(self.exam, action)(*args, **kwargs)
            except ExamAuthError:
                log("考试端凭证已失效，正在重新申请", level="Warning")
        self._authorize(exam_id)
        return getattr(self.exam, action)(*args, **kwargs)

    def check_token(self, exam_id):
        """Return None when the token works, otherwise the failure reason."""
        try:
            self._call(exam_id, "entry_info", exam_id)
        except ExamAuthError as exc:
            return str(exc)
        except PlatformError as exc:
            return str(exc)
        return None

    def _read_paper(self, exam_id):
        paper = self._call(exam_id, "paper", exam_id)
        font = paper.get("font")
        if font:
            paper = json.loads(self.decrypt.get_encrypt_string(
                json.dumps(paper, ensure_ascii=False), font
            ))
        return paper

    @staticmethod
    def _flatten(paper):
        problems = paper.get("problems") or []
        if not paper.get("has_problem_dict"):
            return list(problems)
        flattened = []
        for parent in problems:
            for item in parent.get("problems") or []:
                item = dict(item)
                item["parent_order"] = parent.get("order")
                flattened.append(item)
        return flattened

    @staticmethod
    def _type_of(problem):
        kind = problem.get("Type")
        if kind:
            return kind
        return TYPE_BY_PROBLEM_TYPE.get(problem.get("ProblemType"))

    @classmethod
    def _question(cls, problem):
        problem_type = cls._type_of(problem)
        kind = problem_type
        if kind not in SUPPORTED_TYPES:
            raise ValueError(f"不支持的考试题型：{problem_type}")
        question = {"Type": "SingleChoice" if kind == "Polling" else kind,
                    "Body": problem.get("Body") or ""}
        if kind in ("SingleChoice", "MultipleChoice", "Judgement", "Polling"):
            options = problem.get("Options") or []
            if kind == "Judgement":
                question["Options"] = [
                    f"{option.get('key')}. {option.get('value')}" for option in options
                ]
            else:
                question["Options"] = [
                    f"{_letter(index)}. {option.get('value')}"
                    for index, option in enumerate(options)
                ]
        return question

    @staticmethod
    def _platform_key(problem, letter):
        """Map a displayed option letter back to the platform option key."""
        options = problem.get("Options") or []
        index = _letter_index(letter)
        if not 0 <= index < len(options):
            raise ValueError(f"选项 {letter} 超出题目范围")
        return options[index].get("key")

    def _answer(self, question):
        cached = self.bank.lookup(question)
        if cached is not None:
            try:
                answer = parse_answer(question, cached[0])
                log("题库命中，跳过 AI 请求")
                return answer
            except (ValueError, TypeError):
                self.bank.invalidate(question)
                log("题库答案格式无效，已禁用", level="Warning")
        raw_answer = self.ai.get_answer(
            json.dumps(question, ensure_ascii=False), problem_type=question["Type"]
        )
        return parse_answer(question, raw_answer)

    @classmethod
    def _to_result(cls, problem, answer):
        kind = cls._type_of(problem)
        if kind == "FillBlank":
            if isinstance(answer, dict):
                return {str(index): value for index, value in answer.items()}
            return {"1": str(answer)}
        if kind in ("MultipleChoice", "Polling"):
            return [cls._platform_key(problem, letter) for letter in answer]
        if kind == "Judgement":
            return answer[0] if isinstance(answer, list) else str(answer)
        if kind == "SingleChoice":
            letter = answer[0] if isinstance(answer, list) else str(answer)
            return cls._platform_key(problem, letter)
        if kind == "ShortAnswer":
            text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
            return {"content": text, "attachments": {"filelist": []}, "pics": []}
        raise ValueError(f"不支持的考试题型：{kind}")

    @classmethod
    def _saved_result(cls, problem):
        """Reuse an answer the platform already stored for this paper."""
        kind = cls._type_of(problem)
        if kind == "FillBlank":
            values = problem.get("answerArr") or []
            result = {str(index + 1): str(value).strip()
                      for index, value in enumerate(values)
                      if str(value or "").strip()}
            return result or None
        if kind == "ShortAnswer":
            content = problem.get("result")
            if not isinstance(content, str):
                content = ""
            attachments = problem.get("attachments") or {"filelist": []}
            pics = problem.get("pics") or []
            if not content.strip() and not (attachments.get("filelist") or pics):
                return None
            return {"content": content, "attachments": attachments, "pics": pics}
        value = problem.get("result")
        if value in (None, "", [], {}):
            return None
        return value

    def _exam_status(self, exam_id):
        cover = self._call(exam_id, "cover", exam_id)
        result = cover.get("result") or {}
        status = result.get("status")
        if status is None:
            status = (self._call(exam_id, "entry_info", exam_id) or {}).get("status")
        return int(status or STATUS_NOT_STARTED)

    def _read_results(self, exam_id):
        """Map problem_id -> result for answers the platform already saved."""
        try:
            data = self._call(exam_id, "problem_results", exam_id)
        except PlatformError as exc:
            log(f"读取答题记录失败，忽略已存答案：{exc}", level="Warning")
            return {}
        saved = {}
        for item in data.get("problem_results") or []:
            if not item.get("finished"):
                continue
            result = item.get("result")
            if not result:
                answer = item.get("answer")
                if isinstance(answer, list) and len(answer) == 1:
                    result = answer[0]
                elif answer:
                    result = answer
            if result not in (None, "", [], {}):
                saved[item.get("problem_id")] = result
        return saved

    def do_exam(self, classroom_id, course_sign, course_name):
        leaves = self.leaves(classroom_id, course_sign)
        log(f"{course_name} 共有 {len(leaves)} 场考试")
        all_confirmed = True
        for leaf in leaves:
            if self._stopped():
                return False
            name = leaf.get("name") or "考试"
            try:
                exam_id = self._exam_id(classroom_id, leaf["id"])
                status = self._exam_status(exam_id)
            except ExamAuthError as exc:
                log(f"{name} 读取失败：{exc}；无法自动获取考试凭证", level="Error")
                all_confirmed = False
                continue
            except PlatformError as exc:
                log(f"{name} 读取失败：{exc}", level="Error")
                all_confirmed = False
                continue
            if status >= 2:
                log(f"{name} 已交卷或已结束，跳过", level="Info")
                continue
            if status == STATUS_NOT_STARTED:
                if not self.auto_start:
                    log(f"{name} 尚未开始，未自动开考（自动开考会启动计时）",
                        level="Warning")
                    all_confirmed = False
                    continue
                log(f"{name} 尚未开始，正在开考")
                try:
                    self._call(exam_id, "start", exam_id)
                except PlatformError as exc:
                    log(f"{name} 开始考试失败：{exc}", level="Error")
                    all_confirmed = False
                    continue
            try:
                paper = self._read_paper(exam_id)
            except PlatformError as exc:
                log(f"{name} 取卷失败：{exc}", level="Error")
                all_confirmed = False
                continue
            problems = self._flatten(paper)
            if not problems:
                log(f"{name} 没有可作答的题目", level="Warning")
                all_confirmed = False
                continue
            log(f"{name}（exam_id={exam_id}）共 {len(problems)} 题")
            all_confirmed = self._answer_paper(exam_id, problems, name) and all_confirmed
        return all_confirmed

    def _answer_paper(self, exam_id, problems, title):
        existing = self._read_results(exam_id)
        results = []
        known = set()
        for problem in problems:
            problem_id = problem.get("problem_id")
            result = self._saved_result(problem)
            if result is None and problem_id in existing:
                result = existing[problem_id]
            if result is None:
                continue
            results.append({"problem_id": problem_id, "result": result,
                            "time": int(time.time() * 1000)})
            known.add(problem_id)
        unanswered = []
        for problem in problems:
            if self._stopped():
                return False
            problem_id = problem.get("problem_id")
            if problem_id in known:
                continue
            try:
                answer = self._answer(self._question(problem))
                result = self._to_result(problem, answer)
            except (ValueError, TypeError, KeyError) as exc:
                log(f"题目 {problem_id} 答案无效：{exc}", level="Error")
                unanswered.append(problem_id)
                continue
            entry = {"problem_id": problem_id, "result": result,
                     "time": int(time.time() * 1000)}
            results.append(entry)
            try:
                self._call(exam_id, "save_answers", exam_id, results,
                           [item["problem_id"] for item in results])
            except PlatformError as exc:
                log(f"题目 {problem_id} 保存失败：{exc}", level="Error")
                results.pop()
                unanswered.append(problem_id)
                continue
            known.add(problem_id)
            log(f"题目 {problem_id} 已作答：{result}")
            if not self._pause(random.uniform(0.4, 1.0)):
                return False
        if unanswered:
            log(f"{title} 有 {len(unanswered)} 题未作答：{_format_ids(unanswered)}",
                level="Warning")
        if not results:
            log(f"{title} 没有可提交的答案，暂不交卷", level="Error")
            return False
        try:
            self._call(exam_id, "submit", exam_id, results)
        except PlatformError as exc:
            log(f"{title} 交卷失败：{exc}", level="Error")
            return False
        if unanswered:
            log(f"{title} 已交卷，其中 {len(unanswered)} 题未作答", level="Warning")
            return False
        log(f"{title} 已交卷")
        return True