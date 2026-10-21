"""Local account profiles and stable user agent / proxy pool assignments."""

import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from .config import PROJECT_ROOT
from .platform.auth import extract_specific_cookies


DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


def validate_proxy(value):
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or not parsed.port:
        raise ValueError("代理需使用 http://host:port 或 https://host:port")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("代理地址不能包含路径、查询参数或片段")
    return value


def proxy_label(value):
    if not value:
        return "本机网络"
    parsed = urlsplit(value)
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"


class AccountStore:
    def __init__(self, directory=None):
        self.directory = Path(directory or PROJECT_ROOT / ".accounts")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "profiles.json"
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write({"accounts": [], "user_agents": DEFAULT_USER_AGENTS, "proxies": []})

    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def list(self):
        with self._lock:
            data = self._read()
            return [self._public(account, data) for account in data["accounts"]]

    def pools(self):
        with self._lock:
            data = self._read()
            return {"user_agents": data["user_agents"],
                    "proxies": data["proxies"],
                    "proxy_count": len(data["proxies"])}

    def set_pools(self, user_agents, proxies):
        if not isinstance(user_agents, list) or not user_agents or not all(
            isinstance(item, str) and item.strip() and "\n" not in item and "\r" not in item
            for item in user_agents
        ):
            raise ValueError("UA 池至少需要一条有效的 User-Agent")
        if not isinstance(proxies, list):
            raise ValueError("代理池格式错误")
        proxies = [validate_proxy(item.strip()) for item in proxies if isinstance(item, str) and item.strip()]
        with self._lock:
            data = self._read()
            data["user_agents"] = [item.strip() for item in user_agents]
            data["proxies"] = proxies
            self._write(data)

    def add(self, label, domain, cookie):
        label, domain, cookie = label.strip(), domain.strip().lower(), cookie.strip()
        if not label or len(label) > 80:
            raise ValueError("账号名称需为 1 到 80 个字符")
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError("请输入学校雨课堂域名，例如 buu.yuketang.cn")
        if not all(extract_specific_cookies(cookie)):
            raise ValueError("Cookie 需包含 csrftoken 和 sessionid")
        account_id = uuid4().hex
        with self._lock:
            data = self._read()
            (self.directory / f"{account_id}.txt").write_text(cookie, encoding="utf-8")
            account = {"id": account_id, "label": label, "domain": domain,
                       "slot": len(data["accounts"])}
            data["accounts"].append(account)
            self._write(data)
            return self._public(account, data)

    def remove(self, account_id):
        with self._lock:
            data = self._read()
            before = len(data["accounts"])
            data["accounts"] = [item for item in data["accounts"] if item["id"] != account_id]
            if len(data["accounts"]) == before:
                raise KeyError(account_id)
            self._write(data)
            (self.directory / f"{account_id}.txt").unlink(missing_ok=True)

    def update_cookie(self, account_id, cookie):
        if not isinstance(cookie, str) or not all(extract_specific_cookies(cookie)):
            raise ValueError("Cookie 需包含 csrftoken 和 sessionid")
        with self._lock:
            data = self._read()
            if not any(item["id"] == account_id for item in data["accounts"]):
                raise KeyError(account_id)
            (self.directory / f"{account_id}.txt").write_text(cookie.strip(), encoding="utf-8")

    def get(self, account_id):
        with self._lock:
            data = self._read()
            account = next((item for item in data["accounts"] if item["id"] == account_id), None)
            if account is None:
                raise KeyError(account_id)
            return {
                **account,
                "cookie": (self.directory / f"{account_id}.txt").read_text(encoding="utf-8"),
                "user_agent": data["user_agents"][account["slot"] % len(data["user_agents"])],
                "proxy": (data["proxies"][account["slot"] % len(data["proxies"])]
                          if data["proxies"] else ""),
            }

    @staticmethod
    def _public(account, data):
        slot = account["slot"]
        proxy = data["proxies"][slot % len(data["proxies"])] if data["proxies"] else ""
        return {"id": account["id"], "label": account["label"],
                "domain": account["domain"],
                "user_agent": data["user_agents"][slot % len(data["user_agents"])],
                "proxy": proxy_label(proxy)}
