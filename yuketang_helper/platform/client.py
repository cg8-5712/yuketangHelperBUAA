"""One authenticated HTTP session with finite timeouts."""

import requests
import threading
import random
import time

from ..config import REQUEST_TIMEOUT


class PlatformError(RuntimeError):
    pass


class PlatformClient:
    def __init__(self, domain, university_id, headers=None, session=None, proxy=None):
        self.domain = domain
        self.university_id = str(university_id)
        self._provided_session = session
        self._headers = dict(headers or {})
        self._proxy = proxy
        self._local = threading.local()

    def _session(self):
        if self._provided_session is not None:
            return self._provided_session
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
            self._local.session.headers.update(self._headers)
            if self._proxy:
                self._local.session.proxies.update({"http": self._proxy, "https": self._proxy})
                self._local.session.trust_env = False
        return self._local.session

    @property
    def headers(self):
        return dict(self._headers)

    @property
    def provided_session(self):
        return self._provided_session

    @property
    def proxy(self):
        return self._proxy

    def with_domain(self, domain):
        """Clone this session against another host (for example the exam site)."""
        return PlatformClient(
            domain, self.university_id, self._headers,
            session=self._provided_session, proxy=self._proxy,
        )
    def url(self, path):
        return path if path.startswith(("https://", "http://")) else f"https://{self.domain}{path}"

    def request(self, method, path, *, timeout=REQUEST_TIMEOUT, check_status=True, **kwargs):
        try:
            response = self._session().request(method, self.url(path), timeout=timeout, **kwargs)
            if check_status:
                response.raise_for_status()
            return response
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"HTTP {status}" if status is not None else type(exc).__name__
            raise PlatformError(f"{method} {path} 请求失败：{detail}") from exc

    def get_json(self, path, *, stop_event=None):
        for attempt in range(3):
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("任务已停止")
            try:
                response = self.request("GET", path)
                break
            except PlatformError as exc:
                cause = exc.__cause__
                retryable = isinstance(cause, (requests.Timeout, requests.ConnectionError))
                retryable |= isinstance(cause, requests.HTTPError) and cause.response is not None and cause.response.status_code >= 500
                if not retryable or attempt == 2:
                    raise
                delay = min(2 ** attempt, 4) + random.uniform(0, 0.5)
                if stop_event is not None:
                    if stop_event.wait(delay):
                        raise InterruptedError("任务已停止")
                else:
                    time.sleep(delay)
        try:
            return response.json()
        except ValueError as exc:
            raise PlatformError(f"GET {path} 返回了无效 JSON") from exc

    def post_json(self, path, payload, *, check_status=True, timeout=REQUEST_TIMEOUT):
        # A POST timeout may mean the server accepted the submission. Never
        # retry here; callers that can safely repeat the call must do it.
        response = self.request("POST", path, json=payload,
                                check_status=check_status, timeout=timeout)
        try:
            return response.json()
        except ValueError as exc:
            raise PlatformError(f"POST {path} 返回了无效 JSON") from exc
