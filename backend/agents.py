"""Thin agents operate only on detached data, never files."""
import copy
from pydantic import Field, ValidationError
from .models import Model, World, Review, StateDelta, BranchSet
from .providers import ProviderError


class GeneratedText(Model):
    text: str = Field(min_length=1)


class BaseAgent:
    def __init__(self, provider):
        self.provider = provider

    def invoke(self, task, context, model):
        return model.model_validate(self.provider.complete(
            task, copy.deepcopy(context), model.model_json_schema()))


class DomainAgent:
    key = ""

    def read(self, world):
        return copy.deepcopy(world[self.key])

    def apply(self, candidate, changes):
        entities = {entity["id"]: entity for entity in candidate[self.key]}
        for entity in changes:
            entities[entity["id"]] = copy.deepcopy(entity)
        candidate[self.key] = list(entities.values())


class RoleStateAgent(DomainAgent):
    key = "roles"


class InventoryAgent(DomainAgent):
    key = "inventory"


class MapAgent(DomainAgent):
    key = "maps"


class LoreAgent(DomainAgent):
    key = "lore"


class OutlineAgent(DomainAgent):
    key = "outline"

    def plan(self, world, chapter_number):
        return next((copy.deepcopy(p) for p in world["outline"]["chapters"]
                     if p["chapter_number"] == chapter_number), None)

    def summarize(self, candidate, number, summary):
        for plan in candidate["outline"]["chapters"]:
            if plan["chapter_number"] == number:
                plan["chapter_actual_summary"] = summary


class GeneratorAgent(BaseAgent):
    def generate(self, context):
        return self.invoke("generate: Write the next chapter using the supplied state, "
                           "chapter plan, previous summary and review feedback. The selected_branch is "
                           "the human-selected narrative direction: preserve its chapter_goal, realize "
                           "the main expected_events and character_impacts, and retain its planned hook "
                           "where possible. Do not redesign the core plot or introduce major events "
                           "contradicting this branch. Freely write scenes, dialogue and transitions. "
                           "Do not change state.",
                           context, GeneratedText).text


class ReviewAgent(BaseAgent):
    def review(self, world, text, selected_branch=None):
        result = self.invoke("review: Check the draft against character status (including death, "
                             "injuries, location), item ownership/quantity and unknown items, and lore "
                             "contradictions. Distinguish legitimate events from contradictions. "
                             "Also check plan adherence if selected_branch is supplied: the chapter "
                             "goal, main expected events and strategy must be meaningfully realized. "
                             "Allow paraphrases and creative details, not a verbatim checklist. "
                             "Fail severe plot/strategy deviation and explain specific missing or "
                             "contradictory events. Return passed=false with specific feedback.",
                             {"world": world, "text": text, "selected_branch": selected_branch}, Review)
        if not result.passed and not result.feedback:
            result.feedback = ["机审未通过，请修正正文与世界状态的冲突"]
        return result


class StoryPlannerAgent(BaseAgent):
    def plan(self, world, chapter_plan, previous_summary, recent_changes):
        context = {"world": world, "chapter_number": chapter_plan["chapter_number"],
                   "chapter_plan": chapter_plan, "previous_summary": previous_summary,
                   "recent_state_changes": recent_changes}
        for _ in range(3):
            try:
                result = self.invoke("plan: Propose exactly THREE structured story branches: one "
                                     "progression (steady goal progress), one escalation (increased "
                                     "conflict/risk), one revelation (hidden facts or a new mystery). "
                                     "Keep distinct strategies and IDs. Copy the supplied chapter goal "
                                     "exactly into chapter_goal. Use only existing character IDs in "
                                     "character_impacts. Plan events, never write full chapter prose, "
                                     "select a branch, or modify committed state.", context, BranchSet)
                roles = {role["id"] for role in world["roles"]}
                for branch in result.branches:
                    if branch.chapter_number != chapter_plan["chapter_number"]:
                        raise ValueError("Branch chapter_number does not match current chapter")
                    if branch.chapter_goal != chapter_plan["goal"]:
                        raise ValueError("Branch chapter_goal must preserve the current outline goal")
                    if any(impact.character_id not in roles for impact in branch.character_impacts):
                        raise ValueError("Unknown character_id in character_impacts")
                return result.model_dump()["branches"]
            except (ValidationError, ValueError) as exc:
                context["validation_feedback"] = str(exc)
        raise ProviderError("Planner schema/strategy/chapter validation failed after 3 attempts")


class StateUpdateAgent(BaseAgent):
    def __init__(self, provider):
        super().__init__(provider)
        self.domains = [RoleStateAgent(), InventoryAgent(), MapAgent(), LoreAgent()]
        self.outline = OutlineAgent()

    def extract_and_apply(self, world, text, chapter_number):
        context = {"world": world, "text": text, "chapter_number": chapter_number}
        for attempt in range(3):
            try:
                delta = self.invoke("extract: Extract ONLY changes evidenced by the approved chapter "
                                    "body. Return complete entities for upserts; quantity=0 for consumed "
                                    "items. Include a nonblank chapter_actual_summary of actual events.",
                                    context, StateDelta).model_dump()
                candidate = copy.deepcopy(world)
                for domain in self.domains:
                    domain.apply(candidate, delta[domain.key])
                self.outline.summarize(candidate, chapter_number, delta["chapter_actual_summary"])
                candidate["chapter_number"] = chapter_number
                return World.model_validate(candidate).model_dump()
            except ValidationError as exc:
                context["validation_feedback"] = str(exc)
        raise ProviderError("状态提取连续 3 次未通过 schema 校验，正式状态未修改")


class DirectorAgent(BaseAgent):
    def __init__(self, provider, max_review_retries=2):
        super().__init__(provider)
        self.generator = GeneratorAgent(provider)
        self.reviewer = ReviewAgent(provider)
        self.updater = StateUpdateAgent(provider)
        self.planner = StoryPlannerAgent(provider)
        self.outline = OutlineAgent()
        self.domains = [RoleStateAgent(), InventoryAgent(), MapAgent(), LoreAgent()]
        self.max_review_retries = max_review_retries

    def initialize(self, prompt):
        world = self.invoke("initialize: Convert the user's novel premise into initial roles, "
                            "inventory, maps, lore and a contiguous chapter outline starting at 1. "
                            "Use stable IDs and valid references. chapter_number must be 0; "
                            "all actual summaries must be empty.", {"prompt": prompt}, World)
        if world.chapter_number != 0 or any(p.chapter_actual_summary for p in world.outline.chapters):
            raise ProviderError("初始状态不能包含已批准章节")
        return world.model_dump()

    def generate(self, world, number, selected_branch):
        plan = self.outline.plan(world, number)
        if plan is None:
            from .repository import EngineError
            raise EngineError("当前大纲已结束；本阶段不自动扩展大纲", "outline_exhausted")
        previous = self.outline.plan(world, number - 1)
        context = {"world": {**{a.key: a.read(world) for a in self.domains},
                              "outline": self.outline.read(world),
                              "chapter_number": world["chapter_number"]},
                   "chapter_number": number, "chapter_plan": plan,
                   "previous_summary": previous["chapter_actual_summary"] if previous else "",
                   "review_feedback": [], "selected_branch": copy.deepcopy(selected_branch)}
        for attempt in range(1, self.max_review_retries + 2):
            text = self.generator.generate(context)
            review = self.reviewer.review(world, text, selected_branch)
            if review.passed:
                return text, review, attempt
            context["review_feedback"] = review.feedback
            context["previous_draft"] = text
        return text, review, attempt
