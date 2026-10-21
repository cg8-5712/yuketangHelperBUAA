"""Course and chapter reads."""

from ..models import Course
from .client import PlatformClient, PlatformError


class CourseAPI:
    def __init__(self, client: PlatformClient):
        self.client = client

    def list(self):
        uv = self.client.university_id
        data = self.client.get_json(
            f"/mooc-api/v1/lms/user/user-courses/?status=1&page=1&no_page=1&term=latest&uv_id={uv}"
        )
        try:
            return [Course(**{key: item[key] for key in Course.__dataclass_fields__})
                    for item in data["data"]["product_list"]]
        except (KeyError, TypeError) as exc:
            raise PlatformError("课程列表响应格式错误") from exc

    def chapter(self, classroom_id, course_sign):
        uv = self.client.university_id
        data = self.client.get_json(
            f"/mooc-api/v1/lms/learn/course/chapter?cid={classroom_id}&term=latest&uv_id={uv}&sign={course_sign}"
        )
        try:
            return data["data"]["course_chapter"]
        except (KeyError, TypeError) as exc:
            raise PlatformError("章节列表响应格式错误") from exc

    def leaves(self, classroom_id, course_sign, leaf_type):
        result = []
        for chapter in self.chapter(classroom_id, course_sign):
            for section in chapter.get("section_leaf_list", []):
                for leaf in section.get("leaf_list", [section]):
                    if leaf.get("leaf_type") == leaf_type:
                        result.append(leaf)
        return result

    def leaf_info(self, classroom_id, leaf_id):
        uv = self.client.university_id
        data = self.client.get_json(
            f"/mooc-api/v1/lms/learn/leaf_info/{classroom_id}/{leaf_id}/?term=latest&uv_id={uv}"
        )
        try:
            return data["data"]
        except (KeyError, TypeError) as exc:
            raise PlatformError(f"叶节点 {leaf_id} 响应格式错误") from exc
