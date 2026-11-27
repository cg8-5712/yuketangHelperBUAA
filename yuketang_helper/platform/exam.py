"""Exam room reads and answer saving on the dedicated exam host."""

import time
import urllib.parse

import requests

from ..config import EXAM_LOGIN_TIMEOUT, REQUEST_TIMEOUT
from .client import PlatformClient, PlatformError


EXAM_HOST = "changjiang-exam.yuketang.cn"
EXAM_OK_CODE = 0
TOKEN_PATH = "/v/exam/gen_token"

# Cover/entry status: 0 not started, 1 in progress, >=2 submitted.
STATUS_NOT_STARTED = 0
STATUS_IN_PROGRESS = 1


class ExamAuthError(PlatformError):
    """Raised when the exam host rejects the session (missing or expired token)."""


class ExamAPI:
    """Thin client for /exam_room/* on the exam host.

    ``refresh`` performs the two steps the web client uses: ask the main site
    for a one-time ``crypt`` (``POST /v/exam/gen_token``), then trade it for
    the ``x_access_token`` cookie on ``/login``.
    """

    @staticmethod
    def normalize_host(host):
        """Reduce "https://host/" to a bare host name for URL building."""
        host = (host or "").strip()
        for scheme in ("https://", "http://"):
            if host.startswith(scheme):
                host = host[len(scheme):]
        return host.rstrip("/") or EXAM_HOST

    def __init__(self, client: PlatformClient, host=EXAM_HOST, token=None):
        self.client = client
        self.host = self.normalize_host(host)
        self.token = token
        self.exam = self._session_client(self.host, token, client)

    @classmethod
    def _session_client(cls, host, token, client=None):
        headers = dict(client.headers) if client is not None else {}
        headers["Cookie"] = cls._cookie_with_token(headers.get("Cookie", ""), token)
        headers["Referer"] = f"https://{host}/exam_room/show_paper"
        return PlatformClient(
            host, client.university_id if client is not None else 0, headers,
            session=client.provided_session if client is not None else None,
            proxy=client.proxy if client is not None else None,
        )

    @staticmethod
    def _cookie_with_token(cookie, token):
        parts = [part.strip() for part in cookie.split(";")
                 if part.strip() and not part.strip().startswith("x_access_token=")]
        if token:
            parts.append(f"x_access_token={token}")
        return "; ".join(parts)

    def set_token(self, token, host=None):
        self.token = token
        if host:
            self.host = self.normalize_host(host)
        self.exam = self._session_client(self.host, token, self.client)

    @staticmethod
    def _unwrap(data, action):
        if not isinstance(data, dict):
            raise PlatformError(f"考试{action}响应格式错误")
        errcode = data.get("errcode")
        if errcode in (401, 10011):
            raise ExamAuthError(
                data.get("msg") or data.get("errmsg") or "考试身份认证已失效"
            )
        if errcode not in (None, EXAM_OK_CODE):
            raise PlatformError(
                f"考试{action}失败：{data.get('msg') or data.get('errmsg') or data}"
            )
        return data.get("data")

    def _json(self, method, path, payload=None):
        response = self.exam.request(method, path, json=payload, check_status=False)
        if response.status_code == 401:
            raise ExamAuthError("考试身份认证已失效")
        if response.status_code >= 400:
            raise PlatformError(f"{method} {path} 请求失败：HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise PlatformError(f"{method} {path} 返回了无效 JSON") from exc

    def paper(self, exam_id):
        return self._unwrap(
            self._json("GET", f"/exam_room/show_paper?exam_id={exam_id}"), "取卷"
        ) or {}

    def entry_info(self, exam_id):
        return self._unwrap(
            self._json("GET", f"/exam_room/entry_info?exam_id={exam_id}"), "读取考务信息"
        ) or {}

    def cover(self, exam_id):
        return self._unwrap(
            self._json("GET", f"/exam_room/cover?exam_id={exam_id}"), "读取考试封面"
        ) or {}

    def problem_results(self, exam_id):
        return self._unwrap(
            self._json("GET", f"/exam_room/problem_results?exam_id={exam_id}"),
            "读取答题记录",
        ) or {}

    def cached_results(self, exam_id):
        return self._unwrap(
            self._json("GET", f"/exam_room/cache_results?exam_id={exam_id}"),
            "读取暂存答案",
        ) or {}

    def start(self, exam_id):
        return self._unwrap(
            self._json("POST", "/exam_room/start_paper", {"exam_id": exam_id}), "开始考试"
        )

    def save_answers(self, exam_id, results, record=None):
        payload = {"results": results, "exam_id": exam_id}
        if record is not None:
            payload["record"] = record
        return self._unwrap(
            self._json("POST", "/exam_room/answer_problem", payload), "保存答案"
        )

    def submit(self, exam_id, results):
        return self._unwrap(
            self._json("POST", "/exam_room/submit_paper",
                       {"results": results, "exam_id": exam_id}), "交卷"
        )

    def request_crypt(self, exam_id):
        """Ask the main site for the one-time login credential."""
        data = self.client.post_json(
            TOKEN_PATH, {"exam_id": exam_id}, check_status=False,
            timeout=EXAM_LOGIN_TIMEOUT,
        )
        if not isinstance(data, dict):
            raise PlatformError("考试凭证响应格式错误")
        if data.get("errcode") in (401, 10011):
            raise ExamAuthError("主站登录已失效，无法申请考试凭证")
        auth = data.get("data") if data.get("success") else None
        if not auth or not auth.get("token"):
            raise PlatformError(
                f"申请考试凭证失败：{data.get('errmsg') or data.get('msg') or data}"
            )
        return auth

    def login(self, host, exam_id, user_id, crypt, next_path=None):
        """Trade a one-time crypt for the exam host x_access_token cookie."""
        host = self.normalize_host(host)
        next_path = next_path or f"/exam/{exam_id}?isFrom=1"
        url = (f"https://{host}/login?"
               + urllib.parse.urlencode({
                   "exam_id": exam_id,
                   "user_id": user_id,
                   "crypt": crypt,
                   "next": f"https://{host}{next_path}",
                   "language": "zh",
               }))
        session = requests.Session()
        session.headers.update(self.client.headers)
        if self.client.proxy:
            session.proxies.update({"http": self.client.proxy, "https": self.client.proxy})
            session.trust_env = False
        try:
            response = session.get(url, timeout=EXAM_LOGIN_TIMEOUT,
                                    allow_redirects=False)
        except requests.RequestException as exc:
            raise PlatformError(f"考试登录请求失败：{type(exc).__name__}") from exc
        token = session.cookies.get("x_access_token")
        if not token:
            raise ExamAuthError(
                f"考试登录未返回 x_access_token（HTTP {response.status_code}）"
            )
        return token

    def refresh(self, exam_id):
        """Fetch a fresh exam session and switch this client over to it.

        A crypt is single use, so every attempt mints a new one before the
        login call; retrying the whole pair is therefore safe.
        """
        last = None
        for attempt in range(3):
            try:
                auth = self.request_crypt(exam_id)
                host = auth.get("exam_host") or self.host
                token = self.login(host, exam_id, auth["user_id"], auth["token"])
                self.set_token(token, host=host)
                return token
            except ExamAuthError:
                raise
            except PlatformError as exc:
                last = exc
                cause = exc.__cause__
                retryable = isinstance(cause, (requests.Timeout, requests.ConnectionError))
                if not retryable or attempt == 2:
                    raise
                time.sleep(min(2 ** attempt, 4))
        raise last