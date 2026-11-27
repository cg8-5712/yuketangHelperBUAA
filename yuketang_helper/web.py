"""Loopback-only WebUI for local account and video task management."""

from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .accounts import AccountStore
from .multiuser import TaskManager
from .web_login import QRLoginManager


PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "web_static"
DIST_DIR = PACKAGE_DIR.parent / "webui" / "dist"


def _frontend_dir():
    """Use the Yarn/Vite build when present and keep a zero-build fallback."""
    return DIST_DIR if (DIST_DIR / "index.html").is_file() else STATIC_DIR


def create_app(store=None, manager=None, qr_manager=None, port=8765):
    app = Flask(__name__, static_folder=None)
    store = store or AccountStore()
    manager = manager or TaskManager(store)
    qr_manager = qr_manager or QRLoginManager(store)

    @app.before_request
    def local_json_only():
        host = urlsplit(f"http://{request.host}")
        if host.hostname not in ("127.0.0.1", "localhost") or host.port != port:
            return jsonify(error="仅允许本机访问"), 403
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            if origin:
                parsed = urlsplit(origin)
                allowed_ports = {port, 5173}
                if parsed.hostname not in ("127.0.0.1", "localhost") or parsed.port not in allowed_ports:
                    return jsonify(error="请求来源不匹配"), 403
            if request.method != "DELETE" and not request.is_json:
                return jsonify(error="仅接受 JSON 请求"), 415

    def json_body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    @app.get("/")
    def index():
        return send_from_directory(_frontend_dir(), "index.html")

    @app.get("/app.css")
    def css():
        return send_from_directory(STATIC_DIR, "app.css")

    @app.get("/app.js")
    def javascript():
        return send_from_directory(STATIC_DIR, "app.js")

    @app.get("/vue.global.prod.js")
    def vue_runtime():
        return send_from_directory(STATIC_DIR, "vue.global.prod.js")

    @app.get("/assets/<path:filename>")
    def assets(filename):
        assets_dir = _frontend_dir() / "assets"
        if not assets_dir.is_dir():
            return jsonify(error="前端资源尚未构建，请在 webui 目录执行 yarn build"), 404
        return send_from_directory(assets_dir, filename)

    @app.get("/api/accounts")
    def accounts():
        return jsonify(store.list())

    @app.post("/api/accounts")
    def add_account():
        data = json_body()
        return jsonify(store.add(data.get("label", ""), data.get("domain", ""), data.get("cookie", ""))), 201

    @app.post("/api/login/qr")
    def start_qr_login():
        data = json_body()
        return jsonify(qr_manager.start(data.get("label", ""), data.get("domain", ""))), 201

    @app.get("/api/login/qr/<session_id>")
    def qr_login_status(session_id):
        return jsonify(qr_manager.get(session_id))

    @app.post("/api/login/qr/<session_id>/cancel")
    def cancel_qr_login(session_id):
        return jsonify(qr_manager.cancel(session_id))

    @app.delete("/api/accounts/<account_id>")
    def delete_account(account_id):
        if any(task["account_id"] == account_id and task["status"] in
               ("启动中", "运行中", "停止中") for task in manager.list()):
            return jsonify(error="账号运行中，请先停止任务"), 409
        store.remove(account_id)
        return jsonify(ok=True)

    @app.put("/api/accounts/<account_id>/cookie")
    def update_cookie(account_id):
        if any(task["account_id"] == account_id and task["status"] in
               ("启动中", "运行中", "停止中") for task in manager.list()):
            return jsonify(error="账号运行中，请先停止任务"), 409
        store.update_cookie(account_id, json_body().get("cookie", ""))
        return jsonify(ok=True)

    @app.get("/api/accounts/<account_id>/courses")
    def courses(account_id):
        return jsonify(manager.courses(account_id))

    @app.get("/api/pools")
    def pools():
        return jsonify(store.pools())

    @app.put("/api/pools")
    def set_pools():
        data = json_body()
        store.set_pools(data.get("user_agents"), data.get("proxies"))
        return jsonify(store.pools())

    @app.get("/api/tasks")
    def tasks():
        return jsonify(manager.list())

    @app.post("/api/tasks")
    def start_tasks():
        data = json_body()
        return jsonify(task_ids=manager.start(
            data.get("account_ids"), data.get("course_name"),
            data.get("do_homework", False), data.get("api_mode", "chat_completions"),
            data.get("exam_mode", 0),
        )), 201

    @app.post("/api/tasks/<task_id>/stop")
    def stop_task(task_id):
        manager.stop(task_id)
        return jsonify(ok=True)

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(KeyError)
    def missing(error):
        return jsonify(error=f"未找到：{error.args[0]}"), 404

    @app.errorhandler(Exception)
    def failure(error):
        if isinstance(error, HTTPException):
            return jsonify(error=error.description), error.code
        return jsonify(error="服务器处理失败，请检查终端日志"), 500

    return app


def run_webui(host="127.0.0.1", port=8765):
    app = create_app(port=port)
    print(f"WebUI 已启动：http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
