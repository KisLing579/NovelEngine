"""Atomic canonical JSON plus recoverable, human-readable file projections.

state.json holds the entire committed bundle. One os.replace is the transaction
boundary, including world, chapter records, and snapshots. Other JSON files are
derived exports, repaired under the same inter-process lock before every read.
"""
import copy
import json
import logging
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone
from uuid import uuid4
from filelock import FileLock
from .models import World, PlanningState


class EngineError(RuntimeError):
    def __init__(self, message, code="conflict", status=409, details=None):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details


class StateRepository:
    def __init__(self, directory):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.root / ".repository.lock"), timeout=120)

    def _atomic_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def load(self, repair_exports=True):
        with self.lock:
            path = self.root / "state.json"
            if not path.exists():
                return None
            bundle = json.loads(path.read_text(encoding="utf-8"))
            World.model_validate(bundle["world"])
            self._validate_planning(bundle)
            if repair_exports:
                self._repair_exports(bundle)
            return copy.deepcopy(bundle)

    def save(self, bundle):
        with self.lock:
            World.model_validate(bundle["world"])
            self._validate_planning(bundle)
            # Serialize everything before touching the canonical file.
            json.dumps(bundle, ensure_ascii=False)
            self._atomic_json(self.root / "state.json", bundle)
            self._repair_exports(bundle)

    def _validate_planning(self, bundle):
        for number, planning in bundle.get("narrative_planning", {}).items():
            parsed = PlanningState.model_validate(planning)
            if str(parsed.chapter_number) != number:
                raise ValueError("Planning namespace chapter key mismatch")

    def _repair_exports(self, bundle):
        try:
            self._export(bundle)
        except OSError:
            # The canonical transaction already succeeded. A restart/read repairs
            # exports; never report a committed approval as a failed transaction.
            logging.getLogger(__name__).exception("Derived JSON export needs repair")

    def _export(self, bundle):
        for key in ("roles", "inventory", "maps", "lore", "outline"):
            filename = "lores" if key == "lore" else key
            self._atomic_json(self.root / f"{filename}.json", bundle["world"][key])
        for directory, records, prefix in (
            ("chapters", bundle["chapters"], "chapter_"),
            ("snapshots", bundle["snapshots"], "state_"),
        ):
            folder = self.root / directory
            folder.mkdir(exist_ok=True)
            names = {f"{prefix}{n}.json" for n in records}
            for n, record in records.items():
                self._atomic_json(folder / f"{prefix}{n}.json", record)
            for path in folder.glob(f"{prefix}*.json"):
                if path.name not in names:
                    path.unlink()

    def snapshot(self, bundle):
        key = str(bundle["world"]["chapter_number"])
        bundle["snapshots"][key] = copy.deepcopy(bundle["world"])
        bundle.setdefault("snapshot_metadata", {})[key] = {
            "created_at": datetime.now(timezone.utc).isoformat()}

    def initialize(self, world, project=None):
        with self.lock:
            if self.load() is not None:
                raise EngineError("项目已初始化；请使用回档，不覆盖已有项目")
            bundle = {"schema_version": 1, "revision": uuid4().hex,
                      "world": world, "chapters": {}, "snapshots": {}}
            if project is not None:
                bundle["project"] = project
            self.snapshot(bundle)
            self.save(bundle)
            return bundle

    def rollback(self, chapter_number):
        with self.lock:
            bundle = self.load()
            if bundle is None or str(chapter_number) not in bundle["snapshots"]:
                raise EngineError("目标快照不存在", "not_found", 404)
            bundle["world"] = copy.deepcopy(bundle["snapshots"][str(chapter_number)])
            bundle["revision"] = uuid4().hex
            for key in ("chapters", "snapshots"):
                bundle[key] = {n: v for n, v in bundle[key].items() if int(n) <= chapter_number}
            for key in ("snapshot_metadata", "change_logs", "narrative_planning"):
                if key in bundle:
                    bundle[key] = {n: v for n, v in bundle[key].items() if int(n) <= chapter_number}
            self.save(bundle)
            return bundle
