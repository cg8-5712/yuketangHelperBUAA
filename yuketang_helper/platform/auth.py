"""School discovery, QR login, and cookie storage."""

import json
import re
import time
from pathlib import Path

import requests

from ..config import PROJECT_ROOT, REQUEST_TIMEOUT
from ..logging import log
from .websocket_login import WebSocketQrcode


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def getUniversityId(domain):
    url = f"https://{domain}/edu_admin/get_custom_university_info/?current=1&_={int(time.time() * 1000)}"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    try:
        university_id = response.json()["data"]["university_id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("获取学校 ID 失败：响应格式错误") from exc
    log(f"学校 ID：{university_id}")
    return university_id


def getWebSocketInfo(domain):
    ws = WebSocketQrcode()
    try:
        message = ws.run(domain)
        if not message:
            raise RuntimeError("扫码登录未完成或连接已关闭")
        return message
    finally:
        ws.close()


def exchange_qr_login(domain, university_id, login_message, user_agent=USER_AGENT,
                      session=None):
    """Exchange a successful QR WebSocket message for the platform Cookie."""
    try:
        message = json.loads(login_message) if isinstance(login_message, str) else login_message
        auth_info = message["Auth"]
        user_id = message["UserID"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("扫码登录消息格式错误") from exc
    url = (f"https://{domain}/edu_admin/account/login/verify-origin-system-bind"
           f"?term=latest&uv_id={university_id}")
    headers = {
        "Referer": f"https://{domain}/pro/portal/home/",
        "User-Agent": user_agent,
        "Content-Type": "application/json",
        "Cookie": f"university_id={university_id};platform_id=3;xtbz=cloud;platform_type=1;",
        "Origin": f"https://{domain}",
        "Platform-Id": "3",
        "University-Id": str(university_id),
        "Terminal-Type": "web",
        "X-Client": "web",
        "X-Csrftoken": "undefined",
        "Xtbz": "cloud",
    }
    requester = session or requests
    response = requester.post(
        url, json={"auth": auth_info, "origin_user_id": str(user_id)},
        headers=headers, timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    cookie = response.headers.get("Set-Cookie")
    if not cookie:
        raise RuntimeError("登录未返回 Cookie，请重试")
    return cookie


def getCookies(domain, use_cached=None, filename=None, university_id=None):
    if use_cached is None:
        use_cached = input("是否用已有 cookies？是输入 1：").strip() == "1"
    if filename is None:
        filename = input("请输入 cookies 文件名（不含 .txt）：").strip()
    if not filename:
        raise ValueError("cookies 文件名不能为空")
    cookie_path = Path(filename + ".txt")
    if not cookie_path.is_absolute():
        cookie_path = PROJECT_ROOT / cookie_path
    if use_cached:
        return cookie_path.read_text(encoding="utf-8")

    university_id = university_id or getUniversityId(domain)
    cookie = exchange_qr_login(domain, university_id, getWebSocketInfo(domain))
    cookie_path.write_text(cookie, encoding="utf-8")
    return cookie


def extract_specific_cookies(cookie_string):
    values = {}
    for match in re.finditer(
        r"(?:^|[,;]\s*)(csrftoken|sessionid)=([^;,\s]+)", cookie_string, re.I
    ):
        values[match.group(1).lower()] = match.group(2)
    return values.get("csrftoken"), values.get("sessionid")
