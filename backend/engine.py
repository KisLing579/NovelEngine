from uuid import uuid4
from datetime import datetime, timezone
from .agents import DirectorAgent
from .models import Draft, PlanningState
from .repository import EngineError
from .dashboard import build_dashboard, summarize_changes, planning_for
from .exporter import render_story_pdf
from .text_export import export_chapter_text
from .providers import MockLLMProvider, OpenAICompatibleProvider, DeepSeekProvider, ProviderError


class NovelEngine:
    def __init__(self, repository, provider, max_review_retries=2):
        self.repository = repository
        self.director = DirectorAgent(provider, max_review_retries)
        # Explicit allowlist: never serialize a provider instance or config dict.
        self.provider_info = {"name": type(provider).__name__, "model": None}
        if isinstance(provider, MockLLMProvider):
            self.provider_info = {"name": "MockLLMProvider", "model": "deterministic-mock"}
        elif isinstance(provider, DeepSeekProvider):
            self.provider_info = {"name": "DeepSeekProvider", "model": provider.model}
        elif isinstance(provider, OpenAICompatibleProvider):
            self.provider_info = {"name": "OpenAICompatibleProvider", "model": provider.model}

    def dashboard(self):
        return build_dashboard(self.repository.load(), self.provider_info)

    def pdf_bytes(self):
        return render_story_pdf(self._required())

    def text_download(self):
        return export_chapter_text(self._required())

    def _required(self):
        bundle = self.repository.load()
        if bundle is None:
            raise EngineError("请先初始化项目", "not_initialized")
        return bundle

    def status(self):
        bundle = self.repository.load()
        if bundle is None:
            return {"initialized": False, "chapter_number": 0, "world": None, "draft": None}
        number = bundle["world"]["chapter_number"]
        return {"initialized": True, "chapter_number": number, "world": bundle["world"],
                "draft": bundle["chapters"].get(str(number + 1)),
                "snapshots": sorted(int(n) for n in bundle["snapshots"])}

    def initialize(self, prompt, project=None):
        with self.repository.lock:
            if self.repository.load() is not None:
                raise EngineError("项目已初始化")
            self.repository.initialize(self.director.initialize(prompt), project)
            return self.status()

    def generate(self):
        with self.repository.lock:
            bundle = self._required()
            number = bundle["world"]["chapter_number"] + 1
            planning, branch = self._selected(bundle)
            text, review, attempts = self.director.generate(bundle["world"], number, branch)
            draft = Draft(id=uuid4().hex, chapter_number=number, base_revision=bundle["revision"],
                          text=text, review=review, attempts=attempts,
                          planning_id=planning["id"], selected_branch_id=branch["id"]).model_dump()
            bundle["chapters"][str(number)] = draft
            planning.update(status="draft_generated", draft_id=draft["id"])
            self.repository.save(bundle)
            if not review.passed:
                raise EngineError("机审达到最大重试次数", "review_failed", 422, draft)
            return draft

    def draft(self, number=None):
        with self.repository.lock:
            bundle = self._required()
            number = number if number is not None else bundle["world"]["chapter_number"] + 1
            draft = bundle["chapters"].get(str(number))
            if draft is None:
                raise EngineError("章节不存在", "not_found", 404)
            return draft

    def approve(self, draft_id):
        with self.repository.lock:
            bundle = self._required()
            number = bundle["world"]["chapter_number"] + 1
            draft = bundle["chapters"].get(str(number))
            if not draft or draft["id"] != draft_id or draft["base_revision"] != bundle["revision"]:
                raise EngineError("草稿已过期或不存在，请刷新后重试", "stale_draft")
            if not draft["review"]["passed"] or draft["status"] != "draft":
                raise EngineError("只能批准机审通过的 draft")
            planning, branch = self._selected(bundle)
            if (planning["status"] != "draft_generated" or planning["draft_id"] != draft["id"] or
                    draft.get("planning_id") != planning["id"] or draft.get("selected_branch_id") != branch["id"]):
                raise EngineError("草稿与规划不匹配，请丢弃草稿后重新规划", "planning_mismatch")
            candidate = self.director.updater.extract_and_apply(
                bundle["world"], draft["text"], number)
            changes = summarize_changes(bundle["world"], candidate)
            bundle.setdefault("change_logs", {})[str(number)] = {"chapter": number, "changes": changes}
            bundle["world"] = candidate
            draft["status"] = "approved"
            planning["status"] = "approved"
            bundle["revision"] = uuid4().hex
            self.repository.snapshot(bundle)
            self.repository.save(bundle)
            return self.status()

    def rollback(self, number):
        self.repository.rollback(number)
        return self.status()

    def planning(self, number=None):
        bundle = self._required()
        number = number if number is not None else bundle["world"]["chapter_number"] + 1
        if self.director.outline.plan(bundle["world"], number) is None:
            raise EngineError("该章节不在当前大纲中", "not_found", 404)
        return planning_for(bundle, number)

    def _selected(self, bundle):
        number = bundle["world"]["chapter_number"] + 1
        planning = bundle.get("narrative_planning", {}).get(str(number))
        if not planning or planning["status"] not in ("selected", "draft_generated"):
            raise EngineError("No story branch selected for current chapter.", "branch_not_selected")
        PlanningState.model_validate(planning)
        if planning["chapter_number"] != number or planning["base_revision"] != bundle["revision"]:
            raise EngineError("Planning 与当前章节或世界版本不匹配", "planning_mismatch")
        branch = next((b for b in planning["branches"] if b["id"] == planning["selected_branch_id"]), None)
        plan = self.director.outline.plan(bundle["world"], number)
        if branch is None or not plan or branch["chapter_number"] != number or branch["chapter_goal"] != plan["goal"]:
            raise EngineError("所选路线与当前章节不匹配", "planning_mismatch")
        return planning, branch

    def generate_branches(self, number, regenerate=False, planning_id=None):
        with self.repository.lock:
            bundle = self._required()
            if number != bundle["world"]["chapter_number"] + 1:
                raise EngineError("只能规划当前工作章", "planning_mismatch")
            if str(number) in bundle["chapters"]:
                raise EngineError("请先 Discard Draft，再重新规划或更换路线", "draft_exists")
            current = bundle.get("narrative_planning", {}).get(str(number))
            if regenerate:
                if not current or current["id"] != planning_id:
                    raise EngineError("候选已过期，请刷新", "stale_planning")
            elif current:
                raise EngineError("候选已存在，请使用 Regenerate Story Options", "planning_exists")
            world = bundle["world"]
            plan = self.director.outline.plan(world, number)
            if plan is None:
                raise EngineError("当前大纲已结束", "outline_exhausted")
            previous = self.director.outline.plan(world, number - 1)
            recent = build_dashboard(bundle, self.provider_info)["recent_state_changes"]
            try:
                branches = self.director.planner.plan(world, plan,
                    previous["chapter_actual_summary"] if previous else "", recent)
            except ProviderError as exc:
                raise EngineError("剧情规划调用或结构校验失败；候选数量、策略、ID及章节须合法，未保存新候选",
                                  "planning_failed", 502) from exc
            generation_id = uuid4().hex
            # IDs are validated before qualification. A stale selection can never
            # accidentally select a same-named branch from regenerated options.
            for branch in branches:
                branch["id"] = f"{generation_id}:{branch['id']}"
            state = PlanningState(id=generation_id, chapter_number=number, base_revision=bundle["revision"],
                                  generated_at=datetime.now(timezone.utc).isoformat(),
                                  status="generated", branches=branches).model_dump()
            bundle.setdefault("narrative_planning", {})[str(number)] = state
            self.repository.save(bundle)
            return state

    def select_branch(self, planning_id, branch_id):
        with self.repository.lock:
            bundle = self._required()
            number = bundle["world"]["chapter_number"] + 1
            if str(number) in bundle["chapters"]:
                raise EngineError("已有草稿，请先 Discard Draft 再更换路线", "draft_exists")
            planning = bundle.get("narrative_planning", {}).get(str(number))
            if not planning or planning["id"] != planning_id or planning["base_revision"] != bundle["revision"]:
                raise EngineError("候选已过期或不存在，请刷新", "stale_planning")
            if branch_id not in {b["id"] for b in planning["branches"]}:
                raise EngineError("所选 branch_id 不存在", "invalid_branch", 400)
            planning.update(selected_branch_id=branch_id, selected_at=datetime.now(timezone.utc).isoformat(), status="selected")
            self.repository.save(bundle)
            return planning

    def discard_draft(self, draft_id):
        with self.repository.lock:
            bundle = self._required()
            number = bundle["world"]["chapter_number"] + 1
            draft = bundle["chapters"].get(str(number))
            if not draft or draft["id"] != draft_id or draft["status"] != "draft":
                raise EngineError("草稿不存在或已过期", "stale_draft")
            del bundle["chapters"][str(number)]
            planning = bundle.get("narrative_planning", {}).get(str(number))
            if planning:
                planning.update(status="selected", draft_id=None)
            self.repository.save(bundle)
            return planning_for(bundle, number)
