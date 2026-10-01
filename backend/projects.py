"""Project discovery and selection; every request keeps its own engine binding."""
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from filelock import FileLock

from .engine import NovelEngine
from .repository import EngineError, StateRepository


LEGACY_ID = "@legacy"


class ProjectStore:
    def __init__(self, directory, provider, max_review_retries):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        self.max_review_retries = max_review_retries
        self.engines = {}
        self.cache_lock = RLock()
        self.lock = FileLock(str(self.root / ".projects.lock"), timeout=120)
        self.selection = self.root / ".active-project.json"
        self.empty_engine = NovelEngine(StateRepository(self.root), provider, max_review_retries)

    def directory(self, project_id):
        if project_id == LEGACY_ID:
            return self.root
        if (not isinstance(project_id, str) or not project_id or len(project_id) > 200
                or project_id.startswith(".") or project_id.endswith((".", " "))
                or any(c in project_id for c in '/\\:<>"|?*')
                or any(ord(c) < 32 for c in project_id)):
            raise EngineError("无效的项目 ID", "invalid_request", 400)
        path = self.root / project_id
        if path.is_symlink() or path.resolve().parent != self.root:
            raise EngineError("无效的项目目录", "invalid_request", 400)
        return path

    def engine(self, project_id):
        path = self.directory(project_id)
        if not (path / "state.json").is_file():
            raise EngineError("项目不存在", "not_found", 404)
        with self.cache_lock:
            if project_id not in self.engines:
                self.engines[project_id] = NovelEngine(
                    StateRepository(path), self.provider, self.max_review_retries)
            return self.engines[project_id]

    def active_id(self):
        if self.selection.exists():
            try:
                value = json.loads(self.selection.read_text(encoding="utf-8"))["project_id"]
                if (self.directory(value) / "state.json").is_file():
                    return value
            except (ValueError, KeyError, TypeError, OSError, EngineError):
                pass
        return LEGACY_ID if (self.root / "state.json").is_file() else None

    def resolve(self, project_id=None):
        project_id = project_id if project_id is not None else self.active_id()
        return project_id, self.engine(project_id) if project_id is not None else self.empty_engine

    def select(self, project_id):
        engine = self.engine(project_id)
        try:
            engine.repository.load(repair_exports=False)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise EngineError("项目数据无法读取，请检查 state.json", "invalid_project", 422) from exc
        with self.lock:
            self.empty_engine.repository._atomic_json(self.selection, {"project_id": project_id})
        return engine

    def create(self, prompt, name):
        project_id = uuid4().hex
        engine = NovelEngine(StateRepository(self.directory(project_id)),
                             self.provider, self.max_review_retries)
        engine.initialize(prompt, {"id": project_id, "name": name,
                                   "created_at": datetime.now(timezone.utc).isoformat()})
        with self.cache_lock:
            self.engines[project_id] = engine
        self.select(project_id)
        return project_id, engine

    def list(self):
        ids = [LEGACY_ID] if (self.root / "state.json").is_file() else []
        ids.extend(p.name for p in self.root.iterdir()
                   if p.is_dir() and not p.name.startswith(".") and p.name != LEGACY_ID
                   and not p.is_symlink() and (p / "state.json").is_file())
        projects = []
        for project_id in ids:
            entry = {"id": project_id, "name": "旧版项目（data 根目录）" if project_id == LEGACY_ID else project_id,
                     "available": False, "chapter_number": None, "draft_count": 0,
                     "created_at": None, "updated_at": None, "premise": ""}
            try:
                engine = self.engine(project_id)
                bundle = engine.repository.load(repair_exports=False)
                metadata = bundle.get("project", {})
                entry.update(name=metadata.get("name") or entry["name"],
                             created_at=metadata.get("created_at"),
                             updated_at=datetime.fromtimestamp(
                                 (engine.repository.root / "state.json").stat().st_mtime,
                                 timezone.utc).isoformat(),
                             chapter_number=bundle["world"]["chapter_number"],
                             draft_count=sum(c.get("status") == "draft" for c in bundle["chapters"].values()),
                             premise=bundle["world"]["outline"]["premise"][:200], available=True)
            except (ValueError, KeyError, TypeError, OSError, EngineError):
                entry["error"] = "项目数据无法读取，请检查 state.json"
            projects.append(entry)
        return sorted(projects, key=lambda p: (p["updated_at"] or "", p["id"]), reverse=True)
