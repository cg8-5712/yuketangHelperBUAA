"""Exercise reads and single-attempt submissions."""

import re

from bs4 import BeautifulSoup

from ..models import SubmitResult, SubmitStatus
from .client import PlatformClient, PlatformError


class ExerciseAPI:
    def __init__(self, client: PlatformClient):
        self.client = client

    def list(self, leaf_type_id):
        uv = self.client.university_id
        return self.client.get_json(
            f"/mooc-api/v1/lms/exercise/get_exercise_list/{leaf_type_id}/?term=latest&uv_id={uv}"
        )

    def submit(self, classroom_id, problem_id, answer, fill_blank=False):
        uv = self.client.university_id
        payload = {"classroom_id": classroom_id, "problem_id": problem_id}
        payload["answers" if fill_blank else "answer"] = answer
        data = self.client.post_json(
            f"/mooc-api/v1/lms/exercise/problem_apply/?term=latest&uv_id={uv}",
            payload, check_status=False,
        )
        if not isinstance(data, dict):
            raise PlatformError(f"题目 {problem_id} 提交响应格式错误")
        detail = str(data.get("detail", ""))
        match = re.search(r"Expected available in\s*(\d+(?:\.\d+)?)\s*seconds?", detail)
        if match:
            return SubmitResult(SubmitStatus.RATE_LIMITED, detail, retry_after=float(match.group(1)))
        result = data.get("data")
        if not isinstance(result, dict):
            return SubmitResult(SubmitStatus.FAILED, str(data.get("msg") or "缺少提交结果"))
        explain = result.get("explain")
        explanation = BeautifulSoup(explain, "html.parser").get_text("", strip=True) if isinstance(explain, str) else ""
        if data.get("success") is not True:
            return SubmitResult(SubmitStatus.FAILED, str(data.get("msg") or "提交失败"))
        if result.get("is_right") is True:
            return SubmitResult(SubmitStatus.CORRECT, score=result.get("my_score"), explanation=explanation)
        if result.get("is_right") is False:
            return SubmitResult(SubmitStatus.INCORRECT, score=result.get("my_score"), explanation=explanation)
        return SubmitResult(SubmitStatus.FAILED, "响应未说明答案是否正确")
