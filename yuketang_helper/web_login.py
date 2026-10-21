"""Browser QR-login sessions for the local WebUI."""

import base64
import io
import threading
import time
from uuid import uuid4

import qrcode

from .accounts import DOMAIN_RE, AccountStore
from .platform.auth import exchange_qr_login, getUniversityId
from .platform.websocket_login import WebSocketQrcode


class QRLoginManager:
    def __init__(self, store: AccountStore, max_age=15 * 60):
        self.store = store
        self.max_age = max_age
        self._lock = threading.RLock()
        self._sessions = {}

    def _cleanup(self):
        cutoff = time.time() - self.max_age
        for session_id, session in list(self._sessions.items()):
            if session["created_at"] < cutoff and session["status"] not in ("连接中", "等待扫码"):
                self._sessions.pop(session_id, None)

    @staticmethod
    def _qr_image(value):
        image = qrcode.make(value)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _public(self, session):
        return {
            "id": session["id"],
            "label": session["label"],
            "domain": session["domain"],
            "status": session["status"],
            "qr_image": session.get("qr_image", ""),
            "account_id": session.get("account_id"),
            "error": session.get("error", ""),
        }

    def start(self, label, domain):
        label = (label or "").strip()
        domain = (domain or "").strip().lower()
        if not label:
            label = "扫码账号"
        if len(label) > 80:
            raise ValueError("账号名称需为 1 到 80 个字符")
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError("请输入学校雨课堂域名，例如 buu.yuketang.cn")
        session_id = uuid4().hex
        session = {
            "id": session_id,
            "label": label,
            "domain": domain,
            "status": "连接中",
            "qr_image": "",
            "account_id": None,
            "error": "",
            "created_at": time.time(),
            "stop_event": threading.Event(),
            "ws": None,
            "thread": None,
        }
        with self._lock:
            self._cleanup()
            self._sessions[session_id] = session
            session["thread"] = threading.Thread(
                target=self._run, args=(session_id,), name=f"QRLogin-{session_id[:8]}", daemon=True
            )
            session["thread"].start()
        return self._public(session)

    def get(self, session_id):
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            return self._public(session)

    def cancel(self, session_id):
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            if session["status"] in ("完成", "已取消", "失败"):
                return self._public(session)
            session["status"] = "取消中"
            session["stop_event"].set()
            if session["ws"] is not None:
                session["ws"].close()
            return self._public(session)

    def _set_qr(self, session_id, value):
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session["stop_event"].is_set():
                return
            session["qr_image"] = self._qr_image(value)
            session["status"] = "等待扫码"

    def _run(self, session_id):
        with self._lock:
            session = self._sessions[session_id]
            domain = session["domain"]
            label = session["label"]
            stop_event = session["stop_event"]
        ws = WebSocketQrcode(on_qrcode=lambda value: self._set_qr(session_id, value))
        with self._lock:
            session["ws"] = ws
        try:
            university_id = str(getUniversityId(domain))
            if stop_event.is_set():
                return
            login_message = ws.run(domain)
            if stop_event.is_set():
                return
            if not login_message:
                raise RuntimeError("扫码登录未完成或连接已关闭")
            cookie = exchange_qr_login(domain, university_id, login_message)
            if stop_event.is_set():
                return
            account = self.store.add(label, domain, cookie)
            with self._lock:
                session["account_id"] = account["id"]
                session["status"] = "完成"
        except Exception as exc:
            with self._lock:
                if not stop_event.is_set():
                    session["status"] = "失败"
                    session["error"] = str(exc)
        finally:
            ws.close()
            with self._lock:
                session["ws"] = None
                if session["status"] == "取消中":
                    session["status"] = "已取消"
