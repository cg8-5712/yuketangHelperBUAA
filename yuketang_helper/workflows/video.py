# -*- coding: utf-8 -*-
# version 4
# developed by zk chen
# developed by MuWinds
import random
import time
import re
import threading
from ..logging import log, wait_for_platform
from ..platform.client import PlatformClient
from ..platform.courses import CourseAPI
from ..platform.video import VideoAPI
from ..ui import VideoDashboard


class VideoTaskError(RuntimeError):
    """A worker failed while processing the video queue."""


# 以下字段不用改，下面的代码也不用改动
class videoHelper:
    def __init__(self, domain, cookies, user_id, university_id, learning_rate, header, client=None):

        self.domain = domain
        self.cookies = cookies
        self.user_id = user_id
        self.learning_rate = learning_rate
        self.university_id = university_id
        self.headers = header
        self.client = client or PlatformClient(domain, university_id, header)
        self.courses = CourseAPI(self.client)
        self.videos = VideoAPI(self.client)
        self.stop_event = threading.Event()
        self._worker_errors = []
        self._result_lock = threading.Lock()
        self._incomplete = 0

    def one_video_watcher(self, video_id, video_name, cid, user_id, classroomid, skuid, dashboard=None):
        if self.stop_event.is_set():
            return 0
        if dashboard:
            dashboard.update(video=video_name, status="读取进度", progress=0, detail="")
        video_id = str(video_id)
        classroomid = str(classroomid)
        progress = self.videos.progress(cid, user_id, classroomid, video_id, self.stop_event)
        if progress.get("completed") in (1, True, "1"):
            if dashboard:
                dashboard.update(status="已完成", progress=1, detail="100%")
            log(video_name + "已经学习完毕，跳过")
            return 1
        else:
            log(video_name + "，尚未学习，现在开始自动学习")
            if self.stop_event.wait(2):
                return 0

        # 默认为0（即还没开始看）
        video_frame = 0
        val = 0
        # 获取实际值（观看时长和完成率）
        tmp_rate = progress.get("rate")
        if tmp_rate is None:
            if dashboard:
                dashboard.update(status="无进度数据", detail="")
            return 0
        val = float(tmp_rate)
        video_frame = progress.get("watch_length", 0)
        watch_length_at_last_increase = progress.get("watch_length")
        if dashboard:
            dashboard.update(status="学习中", progress=val, detail=f"{val:.0%}")

        media = self.video_media(classroomid, video_id)
        ccid = str(media.get("ccid") or media.get("cc") or video_id)
        duration = float(media.get("duration") or media.get("video_length") or 0)
        pg_data = f"{video_id}_" + "".join(
            random.sample("zyxwvutsrqponmlkjihgfedcba1234567890", 5)
        )
        t = time.time()
        heart_data = []
        sq = 1
        stagnant_rounds = 0
        while val <= 0.95 and not self.stop_event.is_set():
            base = float(video_frame)
            tp = base if sq > 1 else 0
            now_ms = int(time.time() * 1000)
            seq = sq
            heart_data = []
            for et, cp, event_tp in [
                ("loadstart", base, 0),
                ("play", base, tp),
                ("playing", base, tp),
            ]:
                heart_data.append(self.make_heartbeat(
                    now_ms, seq, et, cp, event_tp, duration, ccid, pg_data,
                    cid, user_id, classroomid, skuid, video_id,
                ))
                seq += 1
            heart_data.append(self.make_heartbeat(
                now_ms, seq, "heartbeat", base + self.learning_rate, tp, duration,
                ccid, pg_data, cid, user_id, classroomid, skuid, video_id,
            ))
            seq += 1
            sq = seq
            data = {"heart_data": heart_data}
            if self.stop_event.is_set():
                return 0
            response_text = self.videos.heartbeat(data)
            match = re.search(
                r"Expected available in\s*(\d+(?:\.\d+)?)\s*seconds?", response_text
            )
            limits = 0
            while match and not self.stop_event.is_set():
                limits += 1
                if limits > 5:
                    raise VideoTaskError(f"视频 {video_id} 连续限流超过 5 次")
                delay = float(match.group(1))
                if dashboard:
                    dashboard.update(status="平台限制，等待", progress=float(val), detail=f"{delay:.0f} s")
                on_tick = (lambda remaining, total: dashboard.update(
                    status="平台限制，等待", progress=1 - remaining / total if total else 1,
                    detail=f"{remaining:.0f} s")) if dashboard else None
                if not wait_for_platform(delay, self.stop_event, on_tick=on_tick):
                    return 0
                if dashboard:
                    dashboard.update(status="学习中", progress=float(val), detail=f"{float(val):.0%}")
                if self.stop_event.wait(0.5):
                    return 0
                response_text = self.videos.heartbeat(data)
                match = re.search(
                    r"Expected available in\s*(\d+(?:\.\d+)?)\s*seconds?", response_text
                )
            video_frame = base + self.learning_rate
            heart_data = []
            if self.stop_event.is_set():
                return 0
            progress = self.videos.progress(cid, user_id, classroomid, video_id, self.stop_event)
            new_rate = progress.get("rate")
            if new_rate is None:
                if dashboard:
                    dashboard.update(status="无进度数据", detail="")
                return 0
            new_rate = float(new_rate)
            reported_length = progress.get("watch_length")
            if new_rate > val:
                watch_length_at_last_increase = reported_length
            stagnant_rounds = stagnant_rounds + 1 if new_rate <= val else 0
            if stagnant_rounds >= 10:
                raise VideoTaskError(
                    f"视频 {video_id} 连续 {stagnant_rounds} 轮进度未增加，"
                    f"平台返回 rate={new_rate:.2%}，"
                    f"watch_length 从 {watch_length_at_last_increase} 变为 {reported_length}"
                )
            val = new_rate
            if dashboard:
                dashboard.update(status="学习中", progress=val, detail=f"{val:.0%}")
            if not dashboard or not dashboard.is_live:
                log(f"{video_name} 学习进度：{val:.2%}")
            if self.stop_event.wait(2):
                return 0
        if self.stop_event.is_set():
            return 0
        if dashboard:
            dashboard.update(status="已完成", progress=1, detail="100%")
        log("视频" + video_id + " " + video_name + "学习完成！")
        return 1

    def video_media(self, classroomid, video_id):
        info = self.courses.leaf_info(classroomid, video_id)
        return info.get("content_info", {}).get("media", {}) or {}

    def make_heartbeat(self, now_ms, sq, et, cp, tp, duration, ccid, pg_data,
                       cid, user_id, classroomid, skuid, video_id):
        return {
            "i": 5,
            "et": et,
            "p": "web",
            "n": "ali-cdn.xuetangx.com",
            "lob": "cloud4",
            "cp": round(float(cp), 1),
            "fp": 0,
            "tp": round(float(tp), 1),
            "sp": 1,
            "ts": str(now_ms),
            "u": int(user_id),
            "uip": "",
            "c": cid,
            "v": int(video_id),
            "skuid": skuid,
            "classroomid": classroomid,
            "cc": ccid,
            "d": round(float(duration), 1) if duration else 0,
            "pg": pg_data,
            "sq": sq,
            "t": "video",
            "cards_id": 0,
            "slide": 0,
            "v_url": "",
        }

    def get_videos_ids(self, course_name, classroom_id, course_sign):
        leaves = self.courses.leaves(classroom_id, course_sign, 0)
        videos = {leaf["id"]: leaf["name"] for leaf in leaves}
        log(f"{course_name} 共有 {len(videos)} 个视频")
        return videos

    def watch_videos(
        self, videos_id_name_dic, course_id, user_id, classroom_id, sku_id, dashboard=None
    ):
        try:
            incomplete = 0
            for one_video in videos_id_name_dic.items():
                if self.stop_event.is_set():
                    if dashboard:
                        dashboard.update(status="已停止", detail="")
                    return
                completed = self.one_video_watcher(
                    one_video[0], one_video[1], course_id, user_id, classroom_id, sku_id, dashboard
                )
                incomplete += not completed
            with self._result_lock:
                self._incomplete += incomplete
            if dashboard:
                dashboard.update(
                    status="部分未完成" if incomplete else "队列完成",
                    detail=f"{incomplete} 个未完成" if incomplete else "",
                )
        except InterruptedError:
            if dashboard:
                dashboard.update(status="已停止", detail="")
            return
        except Exception as exc:
            self._worker_errors.append(exc)
            if dashboard:
                dashboard.update(status="失败", detail=str(exc))
            log(f"视频任务失败：{exc}", level="Error")
            self.stop_event.set()

    def multiple_watch_video(
        self,
        videos_id_name_dic,
        course_id,
        user_id,
        classroom_id,
        sku_id,
        num_workers=4,
        course_name=None,
        dashboard_factory=None,
        reset_stop=True,
    ):
        if reset_stop:
            self.stop_event.clear()
        self._worker_errors = []
        self._incomplete = 0
        parts = list(videos_id_name_dic.items())
        threads = []
        dashboard = (dashboard_factory(course_name or "视频任务", num_workers)
                     if dashboard_factory else VideoDashboard(course_name or "视频任务", workers=num_workers))
        with dashboard:
            for i in range(min(num_workers, len(parts))):
                part = parts[i::num_workers]
                thread = threading.Thread(
                    name=f"Worker{i + 1}",
                    daemon=True,
                    target=self.watch_videos,
                    args=({t[0]: t[1] for t in part}, course_id, user_id,
                          classroom_id, sku_id, dashboard),
                )
                thread.start()
                threads.append(thread)
            try:
                for thread in threads:
                    while thread.is_alive():
                        thread.join(timeout=0.2)
            except KeyboardInterrupt:
                self.stop_event.set()
                log("收到 Ctrl+C，正在停止视频任务")
                for thread in threads:
                    thread.join(timeout=0.2)
                raise SystemExit(130)
            if not threads:
                log("本课程没有视频任务")
        if self._worker_errors:
            cause = self._worker_errors[0]
            raise VideoTaskError(str(cause)) from cause
        return self._incomplete == 0
