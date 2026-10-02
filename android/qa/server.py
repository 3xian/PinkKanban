"""Local Android QA fixture. No database and no production connections.

python android/qa/server.py --port 8765
Build debug with -PkanbanUrl=http://10.0.2.2:8765.
"""
import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
USER = {"id": 1, "display_name": "Android 测试", "email": "android@example.test", "avatar_color": "#7ee9ff"}
QUOTA = {"used": 1, "limit": 30, "remaining": 29}
PROJECT = {"id": 1, "name": "Android 客户端验收", "description": "仅存在于本地的模拟项目", "color": "#7ee9ff",
           "archived": False, "owner_id": 1, "role": "owner", "open_cards": 1, "member_count": 1,
           "updated_at": "2026-10-02T00:00:00Z", "created_at": "2026-10-02T00:00:00Z"}
CARD = {"id": 1, "project_id": 1, "column_id": 1, "title": "验证 Android 附件和返回导航", "description": "本地模拟卡片",
        "excerpt": "本地模拟卡片", "priority": "high", "due_on": None, "cover_color": None, "done": False,
        "archived": False, "position": 0, "created_by": 1, "updated_at": "2026-10-02T00:00:00Z",
        "label_ids": [], "assignee_ids": [1], "checklist": {"done": 0, "total": 0}, "comment_count": 0,
        "attachment_count": 1, "can_edit": True}
FILES = [{"id": 1, "filename": "android-qa.txt", "size": 18, "image": False, "mine": True}]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def translate_path(self, path):
        # Resolve symlinks as well as encoded traversal before serving a file.
        candidate = Path(super().translate_path(path)).resolve()
        return str(candidate) if candidate.is_relative_to(STATIC.resolve()) else str(STATIC / "__not_found__")

    def list_directory(self, path):
        self.send_error(404)
        return None

    def prepare_static_path(self):
        path = urlsplit(self.path).path
        if path == "/":
            self.path = "/index.html"
            return True
        if path.startswith("/static/"):
            relative = path[len("/static/"):]
            if relative and not relative.endswith("/") and not any(
                part in (".", "..") or "\\" in part for part in unquote(relative).split("/")
            ):
                self.path = "/" + relative
                return True
        self.send_error(404)
        return False

    def do_HEAD(self):
        if self.prepare_static_path():
            super().do_HEAD()

    def send_json(self, data, status=200, cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if not path.startswith("/api/"):
            if self.prepare_static_path():
                return super().do_GET()
            return
        if "qa_session=1" not in self.headers.get("Cookie", ""):
            return self.send_json({"detail": "请先登录"}, 401)
        if path == "/api/bootstrap":
            return self.send_json({"user": USER, "projects": [PROJECT], "unread": 0, "quota": QUOTA})
        if path == "/api/projects":
            return self.send_json({"projects": [PROJECT], "quota": QUOTA})
        if path == "/api/projects/1/board":
            return self.send_json({"project": PROJECT, "role": "owner", "members": [{**USER, "role": "owner"}],
                                   "labels": [], "columns": [{"id": 1, "name": "待办", "color": "#7ee9ff", "position": 0,
                                                               "wip_limit": None, "cards": [CARD]}]})
        if path == "/api/cards/1":
            return self.send_json({"card": CARD, "checklists": [], "comments": [], "attachments": FILES, "activity": []})
        if path == "/api/notifications":
            return self.send_json({"items": [], "unread": 0})
        if path == "/api/me/cards":
            return self.send_json({"cards": []})
        if path == "/api/attachments/1/file":
            body = b"Android QA passed\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Disposition", 'attachment; filename="android-qa.txt"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return self.send_json({"detail": "QA fixture has no such endpoint"}, 404)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("X-Kanban") != "1":
            return self.send_json({"detail": "缺少请求头"}, 403)
        if self.path == "/api/auth/login":
            credentials = json.loads(body)
            if credentials != {"email": "android@example.test", "password": "android-qa-pass"}:
                return self.send_json({"detail": "邮箱或密码不正确"}, 401)
            return self.send_json(USER, cookie="qa_session=1; HttpOnly; SameSite=Lax; Path=/; Max-Age=3600")
        if "qa_session=1" not in self.headers.get("Cookie", ""):
            return self.send_json({"detail": "请先登录"}, 401)
        if self.path == "/api/cards/1/attachments":
            if b"Android QA passed" not in body:
                return self.send_json({"detail": "上传文件内容不符"}, 400)
            FILES.append({"id": 2, "filename": "android-qa.txt", "size": 18, "image": False, "mine": True})
            CARD["attachment_count"] = len(FILES)
            return self.send_json(FILES[-1])
        return self.send_json({"detail": "QA fixture has no such endpoint"}, 404)

    def do_PATCH(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("X-Kanban") != "1" or "qa_session=1" not in self.headers.get("Cookie", ""):
            return self.send_json({"detail": "禁止访问"}, 403)
        if self.path == "/api/cards/1":
            CARD.update(json.loads(body))
            return self.send_json({"card": CARD, "checklists": [], "comments": [], "attachments": FILES, "activity": []})
        return self.send_json({"detail": "QA fixture has no such endpoint"}, 404)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
