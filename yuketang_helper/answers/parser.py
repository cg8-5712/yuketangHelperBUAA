"""Normalize answers before submission or storing in SQLite."""

import json
import re


def parse_answer(question, answer):
    kind = question["Type"]
    if kind == "FillBlank":
        if isinstance(answer, str):
            answer = json.loads(answer)
        if not isinstance(answer, dict) or not answer or not all(
            str(key).isdigit() and isinstance(value, str) and value.strip()
            for key, value in answer.items()
        ):
            raise ValueError("填空题答案必须是序号到非空文字的 JSON 对象")
        return {str(key): value.strip() for key, value in answer.items()}
    if kind == "Judgement":
        if isinstance(answer, list) and len(answer) == 1:
            answer = answer[0]
        if isinstance(answer, bool):
            answer = str(answer)
        if isinstance(answer, str) and answer.strip().lower() in ("true", "false"):
            return [answer.strip().lower()]
        raise ValueError("判断题答案应为 true 或 false")
    if kind not in ("SingleChoice", "MultipleChoice"):
        raise ValueError(f"不支持的题型：{kind}")
    values = (
        [part for item in answer for part in re.split(r"[,，、\s]+", str(item).strip())]
        if isinstance(answer, list)
        else re.split(r"[,，、\s]+", str(answer).strip())
    )
    values = [str(value).strip().upper() for value in values if str(value).strip()]
    keys = {str(option).split(".", 1)[0].strip().upper() for option in question.get("Options", [])}
    if not values or any(value not in keys for value in values):
        raise ValueError(f"答案选项不在题目选项中：{values}")
    if kind == "SingleChoice":
        if len(values) != 1:
            raise ValueError("单选题只能提交一个选项")
        return values[0]
    return list(dict.fromkeys(values))
