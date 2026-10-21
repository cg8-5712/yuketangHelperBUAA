"""Optional AI drafted discussion answers with human confirmation."""

from bs4 import BeautifulSoup

from ..logging import log
from ..platform.discussion import DiscussionAPI


class DiscussionWorkflow:
    def __init__(self, courses, client, ai):
        self.courses = courses
        self.api = DiscussionAPI(client)
        self.ai = ai

    def run(self, classroom_id, course_sign):
        leaves = self.courses.leaves(classroom_id, course_sign, 4)
        if not leaves:
            return True
        if input(f"发现 {len(leaves)} 个讨论，是否自动生成并逐题确认？是输入 1：").strip() != "1":
            return False
        all_confirmed = True
        for leaf in leaves:
            leaf_id = leaf["id"]
            info = self.courses.leaf_info(classroom_id, leaf_id)
            if info.get("finish"):
                log(f"讨论 {leaf_id} 已完成")
                continue
            context = info.get("content_info", {}).get("context", "")
            query = BeautifulSoup(context, "html.parser").get_text(" ", strip=True)
            topic = self.api.topic(classroom_id, info["sku_id"], info["id"])
            answer = self.ai.get_answer(query, leaf_type=4)
            while True:
                log(f"讨论 {leaf_id}：{query}")
                log(f"建议回答：{answer}")
                choice = input("回车确认并提交；1 重新生成；2 跳过：").strip()
                if choice == "1":
                    suggestion = input("修改建议：").strip()
                    answer = self.ai.get_answer(
                        f"问题：{query}\n之前的答案：{answer}\n修改建议：{suggestion}", leaf_type=4
                    )
                    continue
                if choice == "2":
                    log(f"讨论 {leaf_id} 已跳过")
                    all_confirmed = False
                    break
                result = self.api.submit(topic["user_id"], topic["id"], answer)
                if result.get("success") is True:
                    log(f"讨论 {leaf_id} 提交成功")
                else:
                    log(f"讨论 {leaf_id} 提交失败：{result.get('msg', '未知原因')}", level="Error")
                    all_confirmed = False
                break
        return all_confirmed
