"""Video progress and heartbeat endpoints."""

from .client import PlatformClient, PlatformError


class VideoAPI:
    def __init__(self, client: PlatformClient):
        self.client = client

    def progress(self, course_id, user_id, classroom_id, video_id, stop_event=None):
        uv = self.client.university_id
        path = (f"/video-log/get_video_watch_progress/?cid={course_id}&user_id={user_id}"
                f"&classroom_id={classroom_id}&video_type=video&vtype=rate"
                f"&video_id={video_id}&snapshot=1&term=latest&uv_id={uv}")
        data = self.client.get_json(path, stop_event=stop_event)
        try:
            return data["data"][str(video_id)]
        except (KeyError, TypeError) as exc:
            raise PlatformError(f"视频 {video_id} 进度响应格式错误") from exc

    def heartbeat(self, payload):
        # The platform may return a rate-limit message with a non-2xx status.
        response = self.client.request(
            "POST", "/video-log/heartbeat/", json=payload, check_status=False
        )
        if response.status_code >= 400 and "Expected available in" not in response.text:
            raise PlatformError(f"视频心跳返回 HTTP {response.status_code}")
        return response.text
