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
        if not isinstance(data, dict):
            raise PlatformError(f"视频 {video_id} 进度响应格式错误：顶层应为对象")
        if "code" in data and data["code"] != 0:
            message = data.get("message") or data.get("msg") or "平台未提供错误说明"
            raise PlatformError(
                f"视频 {video_id} 进度查询失败：code={data['code']}，{str(message)[:200]}"
            )
        records = data.get("data")
        # A successful query returns an empty object before a watch record exists.
        # Do not treat missing/null data or an API error as an unwatched video.
        if data.get("code") == 0 and records == {}:
            return {"completed": 0, "rate": 0, "watch_length": 0}
        try:
            progress = records[str(video_id)]
        except (KeyError, TypeError) as exc:
            raise PlatformError(f"视频 {video_id} 进度响应格式错误") from exc
        if not isinstance(progress, dict):
            raise PlatformError(f"视频 {video_id} 进度响应格式错误：进度记录应为对象")
        return progress

    def playurl(self, ccid):
        params = {
            "video_id": ccid,
            "provider": "cc",
            "file_type": "1",
            "is_single": "0",
            "domain": self.client.domain,
        }
        data = self.client.get_json("/api/open/audiovideo/playurl?" + "&".join(
            f"{key}={value}" for key, value in params.items()
        ))
        try:
            sources = data["data"]["playurl"]["sources"]
        except (KeyError, TypeError) as exc:
            raise PlatformError(f"视频 {ccid} 播放直链响应格式错误") from exc
        for quality in ("quality20", "quality10"):
            urls = sources.get(quality) or []
            if urls:
                return urls[0]
        raise PlatformError(f"视频 {ccid} 未返回可用的播放直链")

    def mp4_duration(self, url):
        # Parse top-level MP4 boxes with range requests to read mvhd only.
        response = self.client.request("GET", url, headers={"Range": "bytes=0-1"})
        if response.status_code not in (200, 206):
            raise PlatformError(f"MP4 无法访问：HTTP {response.status_code}")

        def head(offset, length):
            data = self.client.request(
                "GET", url, headers={"Range": f"bytes={offset}-{offset + length - 1}"}
            )
            content = data.content
            if len(content) != length:
                raise PlatformError("MP4 范围读取失败")
            return content

        pos = 0
        for _ in range(64):
            header = head(pos, 8)
            size = int.from_bytes(header[:4], "big")
            box_type = header[4:8]
            if size == 1:
                header = head(pos + 8, 8)
                size = int.from_bytes(header, "big")
            if size < 8:
                raise PlatformError("MP4 box 大小异常")
            if box_type == b"moov":
                inner_pos = pos + 8
                end = pos + size
                for _ in range(256):
                    child = head(inner_pos, 8)
                    child_size = int.from_bytes(child[:4], "big")
                    child_type = child[4:8]
                    if child_size < 8 or inner_pos + child_size > end:
                        break
                    if child_type == b"mvhd":
                        mvhd = head(inner_pos, min(child_size, 128))
                        version = mvhd[8]
                        if version == 1:
                            timescale = int.from_bytes(mvhd[28:32], "big")
                            duration = int.from_bytes(mvhd[32:40], "big")
                        else:
                            timescale = int.from_bytes(mvhd[20:24], "big")
                            duration = int.from_bytes(mvhd[24:28], "big")
                        if not timescale:
                            raise PlatformError("MP4 mvhd timescale 为 0")
                        return duration / timescale
                    inner_pos += child_size
                raise PlatformError("MP4 moov 中未找到 mvhd")
            pos += size

        raise PlatformError("MP4 顶层未找到 moov")

    def heartbeat(self, payload):
        # The platform may return a rate-limit message with a non-2xx status.
        response = self.client.request(
            "POST", "/video-log/heartbeat/", json=payload, check_status=False
        )
        if response.status_code >= 400 and "Expected available in" not in response.text:
            raise PlatformError(f"视频心跳返回 HTTP {response.status_code}")
        return response.text
