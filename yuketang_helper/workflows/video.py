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
        if dashboard:
            dashboard.update(status="学习中", progress=val, detail=f"{val:.0%}")

        t = time.time()
        timstap = int(round(t * 1000))
        heart_data = []
        stagnant_rounds = 0
        while val <= 0.95 and not self.stop_event.is_set():
            for i in range(3):
                heart_data.append(
                    {
                        "i": 5,
                        "et": "loadeddata",
                        "p": "web",
                        "n": "ali-cdn.xuetangx.com",
                        "lob": "cloud4",
                        "cp": video_frame,
                        "fp": 0,
                        "tp": 0,
                        "sp": 2,
                        "ts": str(timstap),
                        "u": int(user_id),
                        "uip": "",
                        "c": cid,
                        "v": int(video_id),
                        "skuid": skuid,
                        "classroomid": classroomid,
                        "cc": video_id,
                        "d": 4976.5,
                        "pg": video_id
                        + "_"
                        + "".join(
                            random.sample("zyxwvutsrqponmlkjihgfedcba1234567890", 4)
                        ),
                        "sq": i + 1,
                        "t": "video",
                    }
                )
                video_frame += self.learning_rate
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
                    raise RuntimeError(f"视频 {video_id} 连续限流超过 5 次")
                delay = float(match.group(1))
                if dashboard:
                    dashboard.update(status="平台限制，等待", progress=0, detail=f"{delay:.0f} s")
                on_tick = (lambda remaining, total: dashboard.update(
                    status="平台限制，等待", progress=1 - remaining / total if total else 1,
                    detail=f"{remaining:.0f} s")) if dashboard else None
                if not wait_for_platform(delay, self.stop_event, on_tick=on_tick):
                    return 0
                if dashboard:
                    dashboard.update(status="学习中", progress=float(val), detail=f"{float(val):.0%}")
                if self.stop_event.wait(0.5):
                    return 0
                if self.stop_event.is_set():
                    return 0
                response_text = self.videos.heartbeat(data)
                match = re.search(
                    r"Expected available in\s*(\d+(?:\.\d+)?)\s*seconds?", response_text
                )
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
            stagnant_rounds = stagnant_rounds + 1 if new_rate <= val else 0
            if stagnant_rounds >= 10:
                raise RuntimeError(f"视频 {video_id} 连续 10 次心跳后进度未增加")
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
            raise RuntimeError("视频任务失败") from self._worker_errors[0]
        return self._incomplete == 0
