"""Discussion topic reads and single-attempt comment submission."""

import time

from .client import PlatformClient, PlatformError


class DiscussionAPI:
    def __init__(self, client: PlatformClient):
        self.client = client

    def topic(self, classroom_id, sku_id, leaf_id):
        stamp = int(time.time() * 1000)
        path = (f"/v/discussion/v2/unit/discussion/?_date={stamp}&term=latest"
                f"&classroom_id={classroom_id}&sku_id={sku_id}&leaf_id={leaf_id}"
                "&topic_type=4&channel=xt")
        data = self.client.get_json(path)
        try:
            return data["data"]
        except (KeyError, TypeError) as exc:
            raise PlatformError(f"讨论 {leaf_id} 话题响应格式错误") from exc

    def submit(self, to_user, topic_id, answer):
        uv = self.client.university_id
        return self.client.post_json(
            f"/v/discussion/v2/comment/?term=latest&uv_id={uv}",
            {"to_user": to_user, "topic_id": topic_id,
             "content": {"text": answer, "upload_images": [], "accessory_list": []},
             "anchor": 0},
        )
