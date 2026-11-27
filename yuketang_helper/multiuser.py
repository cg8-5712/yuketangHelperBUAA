"""Independent account tasks for the local WebUI."""

import threading
import time
from uuid import uuid4

from .accounts import AccountStore
from .cli import build_headers
from .platform.client import PlatformClient
from .platform.courses import CourseAPI
from .ui import VideoDashboard
from .workflows.video import videoHelper
from .workflows.exam import examHelper
from .workflows.homework import homeworkHelper


class TaskManager:
    def __init__(self, store: AccountStore, max_accounts=8):
        self.store = store
        self.max_accounts = max_accounts
        self._lock = threading.RLock()
        self._tasks = {}

    def _client_for(self, account):
        discovery = PlatformClient(
            account["domain"], "", {"User-Agent": account["user_agent"]},
            proxy=account["proxy"],
        )
        stamp = int(time.time() * 1000)
        data = discovery.get_json(f"/edu_admin/get_custom_university_info/?current=1&_={stamp}")
        university_id = str(data["data"]["university_id"])
        headers = build_headers(account["cookie"], university_id)
        headers["User-Agent"] = account["user_agent"]
        return PlatformClient(account["domain"], university_id, headers, proxy=account["proxy"])

    def courses(self, account_id):
        account = self.store.get(account_id)
        client = self._client_for(account)
        session = client.get_json("/edu_admin/check_user_session/")
        user_id = str((session.get("data") or session)["user_id"])
        courses = CourseAPI(client).list()
        return {"user_id": user_id,
                "courses": [{"id": course.course_name, "name": course.course_name}
                            for course in courses]}

    def list(self):
        with self._lock:
            return [self._public(task) for task in self._tasks.values()]

    def _public(self, task):
        return {key: value for key, value in task.items()
                if key not in ("thread", "stop_event", "helper")}

    def start(self, account_ids, course_name=None, do_homework=False,
              api_mode="chat_completions", exam_mode=0):
        if not isinstance(account_ids, list) or not account_ids or not all(
            isinstance(account_id, str) for account_id in account_ids
        ):
            raise ValueError("请至少选择一个账号")
        if course_name is not None and not isinstance(course_name, str):
            raise ValueError("课程名称格式错误")
        if len(set(account_ids)) != len(account_ids):
            raise ValueError("账号不能重复")
        accounts = [self.store.get(account_id) for account_id in account_ids]
        if api_mode not in ("chat_completions", "responses"):
            raise ValueError("AI 接口选择无效")
        if exam_mode not in (0, 1, 2):
            raise ValueError("考试模式选择无效")
        with self._lock:
            active = sum(task["status"] in ("启动中", "运行中", "停止中")
                         for task in self._tasks.values())
            if active + len(accounts) > self.max_accounts:
                raise ValueError(f"最多同时运行 {self.max_accounts} 个账号")
            for account_id in account_ids:
                if any(task["account_id"] == account_id and task["status"] in
                       ("启动中", "运行中", "停止中") for task in self._tasks.values()):
                    raise ValueError("所选账号已有运行中的任务")
            result = []
            for account in accounts:
                task_id = uuid4().hex
                task = {"id": task_id, "account_id": account["id"],
                        "label": account["label"], "status": "启动中",
                        "course": "", "workers": {}, "error": "", "course_name": course_name,
                        "do_homework": bool(do_homework), "api_mode": api_mode,
                        "exam_mode": int(exam_mode or 0),
                        "stop_event": threading.Event(), "helper": None, "thread": None}
                self._tasks[task_id] = task
                result.append(task_id)
            for task_id in result:
                task = self._tasks[task_id]
                task["thread"] = threading.Thread(
                    target=self._run, args=(task_id,), name=f"Account-{task['label']}", daemon=True
                )
                task["thread"].start()
            return result

    def stop(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task["status"] not in ("启动中", "运行中", "停止中"):
                return
            task["status"] = "停止中"
            task["stop_event"].set()
            if task["helper"] is not None:
                task["helper"].stop_event.set()

    def stop_all(self):
        for task in self.list():
            self.stop(task["id"])

    def _update_worker(self, task_id, worker, row):
        with self._lock:
            self._tasks[task_id]["workers"][worker] = row

    def _run(self, task_id):
        with self._lock:
            task = self._tasks[task_id]
            account_id, stop_event, course_name = task["account_id"], task["stop_event"], task["course_name"]
            do_homework, api_mode = task["do_homework"], task["api_mode"]
            exam_mode = task.get("exam_mode", 0)
        try:
            account = self.store.get(account_id)
            client = self._client_for(account)
            if stop_event.is_set():
                return
            session = client.get_json("/edu_admin/check_user_session/", stop_event=stop_event)
            user_id = str((session.get("data") or session)["user_id"])
            courses = CourseAPI(client).list()
            if course_name is not None:
                courses = [course for course in courses if course.course_name == course_name]
                if not courses:
                    raise ValueError("选定课程不属于该账号")
            helper = videoHelper(
                account["domain"], account["cookie"], user_id,
                client.university_id, 12, client._headers, client=client,
            )
            with self._lock:
                task["helper"] = helper
                if stop_event.is_set():
                    helper.stop_event.set()
                else:
                    task["status"] = "运行中"
            complete = True
            for course in courses:
                if stop_event.is_set():
                    break
                with self._lock:
                    task["course"] = course.course_name
                    task["workers"] = {}
                videos = helper.get_videos_ids(
                    course.course_name, course.classroom_id, course.course_sign
                )
                if stop_event.is_set():
                    break
                def dashboard_factory(name, workers):
                    return VideoDashboard(
                        name, workers, live=False,
                        on_update=lambda worker, row: self._update_worker(task_id, worker, row),
                    )
                complete = helper.multiple_watch_video(
                    videos, course.course_id, user_id, course.classroom_id,
                    course.sku_id, course_name=course.course_name,
                    dashboard_factory=dashboard_factory,
                    reset_stop=False,
                ) and complete
            if do_homework and not stop_event.is_set():
                homework = homeworkHelper(
                    account["domain"], account["cookie"], user_id,
                    client.university_id, client._headers, api_mode=api_mode,
                    client=client, stop_event=stop_event, run_discussions=False,
                )
                for course in courses:
                    if stop_event.is_set():
                        break
                    with self._lock:
                        task["course"] = f"{course.course_name} · 习题"
                        task["workers"] = {}
                    complete = homework.do_homework(
                        course.classroom_id, course.course_sign, course.course_name
                    ) and complete
            if exam_mode and not stop_event.is_set():
                exam = examHelper(
                    account["domain"], account["cookie"], user_id,
                    client.university_id, client._headers, api_mode=api_mode,
                    client=client, stop_event=stop_event, auto_start=exam_mode == 2,
                )
                for course in courses:
                    if stop_event.is_set():
                        break
                    with self._lock:
                        task["course"] = f"{course.course_name} · 考试"
                        task["workers"] = {}
                    complete = exam.do_exam(
                        course.classroom_id, course.course_sign, course.course_name
                    ) and complete
            with self._lock:
                task["status"] = ("已停止" if stop_event.is_set()
                                  else "已完成" if complete else "部分未完成")
        except InterruptedError:
            with self._lock:
                task["status"] = "已停止"
        except Exception as exc:
            with self._lock:
                task["status"] = "已停止" if stop_event.is_set() else "失败"
                if not stop_event.is_set():
                    message = str(exc)
                    account_proxy = account.get("proxy", "") if "account" in locals() else ""
                    if account_proxy:
                        message = message.replace(account_proxy, "[代理地址]")
                    task["error"] = message
        finally:
            with self._lock:
                if task["status"] == "停止中":
                    task["status"] = "已停止"
                task["helper"] = None
