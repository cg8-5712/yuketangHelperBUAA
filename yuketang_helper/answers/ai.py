"""Chat Completions and Responses adapter."""

import re

from openai import OpenAI

from ..config import load_ai_config


DISCUSSION_PROMPT = (
    "以一个大学生或研究生的视角，回答讨论问题，约 300 字。"
    "内容连贯自然，直接回答，不使用 Markdown。"
)


class OpenAI_ask:
    def __init__(self, api_mode="chat_completions", config=None, client=None):
        if api_mode not in ("chat_completions", "responses"):
            raise ValueError(f"不支持的 AI 接口：{api_mode}")
        self.api_mode = api_mode
        self.config = config or load_ai_config()
        self.client = client or OpenAI(
            api_key=self.config["key"], base_url=self.config["base_url"]
        )

    def get_answer(self, problem, problem_type="Choice", leaf_type=6):
        prompt = DISCUSSION_PROMPT if leaf_type == 4 else self.config["system_prompt"]
        if self.api_mode == "responses":
            response = self.client.responses.create(
                model=self.config["model"], instructions=prompt, input=problem
            )
            content = response.output_text
        else:
            response = self.client.chat.completions.create(
                model=self.config["model"],
                messages=[{"role": "system", "content": prompt},
                          {"role": "user", "content": problem}],
                temperature=0.7,
            )
            content = response.choices[0].message.content
        if not content:
            raise ValueError("模型未返回文本答案，请检查接口和模型配置")
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if problem_type == "FillBlank" and content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        return content
