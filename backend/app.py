import os
from urllib.parse import unquote
from pathlib import Path
from flask import Flask, Response, jsonify, request, g
from filelock import Timeout
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException
from werkzeug.local import LocalProxy
from .projects import ProjectStore
from .providers import ProviderError
from .configuration import load_settings, create_provider
from .repository import EngineError


def create_app(data_dir=None, provider=None, config=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    settings = load_settings(config)
    if type(settings["max_review_retries"]) is not int or not 0 <= settings["max_review_retries"] <= 10:
        raise ValueError("max_review_retries must be an integer between 0 and 10")
    if provider is None:
        provider = create_provider(settings)
    projects = ProjectStore(data_dir or os.getenv("NOVEL_DATA_DIR") or
                            Path(__file__).with_name("data"), provider, settings["max_review_retries"])
    app.extensions["projects"] = projects
    app.extensions["novel_engine"] = projects.resolve()[1]
    engine = LocalProxy(lambda: g.novel_engine)

    @app.before_request
    def bind_project():
        # Never mutate a shared engine's repository during a project switch.
        # Browser requests carry an explicit ID, isolating concurrent tabs too.
        if request.path in ("/api/projects", "/api/project/init", "/api/project/load"):
            g.project_id, g.novel_engine = None, projects.empty_engine
        else:
            header_id = request.headers.get("X-Project-ID")
            project_id = unquote(header_id) if header_id is not None else request.args.get("project_id")
            g.project_id, g.novel_engine = projects.resolve(project_id)

    def success(data):
        return jsonify({"ok": True, "data": data, "error": None})

    def body():
        data = request.get_json()
        if not isinstance(data, dict):
            raise EngineError("请求正文必须是 JSON 对象", "invalid_request", 400)
        return data

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, EngineError):
            message, code, status, details = str(exc), exc.code, exc.status, exc.details
        elif isinstance(exc, HTTPException):
            message, code, status, details = exc.description, "http_error", exc.code, None
        elif isinstance(exc, (ProviderError, ValidationError)):
            message = (str(exc) if isinstance(exc, ProviderError) else "模型输出未通过结构校验") + "；正式状态未修改"
            code, status, details = "provider_error", 502, None
            app.logger.warning("Provider error: %s", type(exc).__name__)
        elif isinstance(exc, Timeout):
            message, code, status, details = "项目正在处理其他请求，请稍后重试", "busy", 409, None
        else:
            app.logger.exception("Unhandled error")
            message, code, status, details = "服务器内部错误，请查看日志", "internal_error", 500, None
        return jsonify({"ok": False, "data": None,
                        "error": {"code": code, "message": message, "details": details}}), status

    @app.get("/api/project/status")
    def status():
        return success({**engine.status(), "project_id": g.project_id})

    @app.get("/api/dashboard")
    def dashboard():
        data = engine.dashboard()
        history = projects.list()
        data.update(project_id=g.project_id, projects=history)
        if data["project"]:
            data["project"]["id"] = g.project_id
            data["project"]["name"] = next((p["name"] for p in history if p["id"] == g.project_id), None)
        return success(data)

    @app.get("/api/projects")
    def project_history():
        return success({"projects": projects.list(), "active_project_id": projects.active_id()})

    @app.post("/api/project/load")
    def load_project():
        project_id = body().get("project_id")
        if not isinstance(project_id, str) or not project_id:
            raise EngineError("project_id 是必填字符串", "invalid_request", 400)
        selected = projects.select(project_id)
        app.extensions["novel_engine"] = selected
        return success({**selected.status(), "project_id": project_id})

    @app.post("/api/project/init")
    def initialize():
        data = body()
        prompt = data.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
            raise EngineError("prompt 必须是 1–20000 字符的非空文本", "invalid_request", 400)
        name = data.get("name", prompt.strip().splitlines()[0][:80])
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise EngineError("name 必须是 1–80 字符的非空文本", "invalid_request", 400)
        project_id, created = projects.create(prompt.strip(), name.strip())
        app.extensions["novel_engine"] = created
        return success({**created.status(), "project_id": project_id})

    @app.get("/api/project/export/pdf")
    def export_pdf():
        return Response(engine.pdf_bytes(), mimetype="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="novel.pdf"'})

    @app.get("/api/project/export/txt")
    def export_txt():
        content, filename, content_type = engine.text_download()
        return Response(content, content_type=content_type, headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        })

    @app.post("/api/chapter/generate")
    def generate():
        if request.data and body():
            raise EngineError("Generate 仅从后端读取已选路线，不接受请求中的规划或正文", "invalid_request", 400)
        return success(engine.generate())

    def required_text(data, name):
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            raise EngineError(f"{name} 是必填字符串", "invalid_request", 400)
        return value

    def branch_generation(regenerate=False):
        data = body()
        number = data.get("chapter_number")
        if type(number) is not int or number < 1:
            raise EngineError("chapter_number 必须是正整数", "invalid_request", 400)
        planning_id = required_text(data, "planning_id") if regenerate else None
        return success(engine.generate_branches(number, regenerate, planning_id))

    @app.get("/api/chapter/planning/")
    @app.get("/api/chapter/planning/<int:number>")
    def planning(number=None):
        return success(engine.planning(number))

    @app.post("/api/chapter/branches/generate")
    def branches_generate():
        return branch_generation()

    @app.post("/api/chapter/branches/regenerate")
    def branches_regenerate():
        return branch_generation(True)

    @app.post("/api/chapter/branches/select")
    def branches_select():
        data = body()
        return success(engine.select_branch(required_text(data, "planning_id"), required_text(data, "branch_id")))

    @app.post("/api/chapter/draft/discard")
    def discard():
        return success(engine.discard_draft(required_text(body(), "draft_id")))

    @app.get("/api/chapter/draft/")
    @app.get("/api/chapter/draft/<int:number>")
    def draft(number=None):
        return success(engine.draft(number))

    @app.post("/api/chapter/approve")
    def approve():
        draft_id = body().get("draft_id")
        if not isinstance(draft_id, str) or not draft_id:
            raise EngineError("draft_id 是必填字符串", "invalid_request", 400)
        return success(engine.approve(draft_id))

    @app.post("/api/project/rollback")
    def rollback():
        number = body().get("chapter_number")
        if type(number) is not int or number < 0:
            raise EngineError("chapter_number 必须是非负整数", "invalid_request", 400)
        return success(engine.rollback(number))

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
