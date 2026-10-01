"""Explicit schemas shared by agents, providers, and persistence."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Role(Model):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    alive: bool = True
    condition: str = "健康"
    location_id: str


class Item(Model):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    owner_id: str
    quantity: int = Field(ge=0)


class Place(Model):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str


class Lore(Model):
    id: str = Field(min_length=1)
    fact: str = Field(min_length=1)


class ChapterPlan(Model):
    chapter_number: int = Field(ge=1)
    goal: str = Field(min_length=1)
    chapter_actual_summary: str = ""


class Outline(Model):
    premise: str = Field(min_length=1)
    chapters: list[ChapterPlan] = Field(min_length=1)


class World(Model):
    schema_version: Literal[1] = 1
    chapter_number: int = Field(default=0, ge=0)
    roles: list[Role] = Field(min_length=1)
    inventory: list[Item]
    maps: list[Place] = Field(min_length=1)
    lore: list[Lore]
    outline: Outline

    @model_validator(mode="after")
    def consistent(self):
        for values in (self.roles, self.inventory, self.maps, self.lore):
            ids = [v.id for v in values]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate entity IDs")
        roles = {r.id for r in self.roles}
        maps = {m.id for m in self.maps}
        if any(r.location_id not in maps for r in self.roles):
            raise ValueError("Unknown role location")
        if any(i.owner_id not in roles for i in self.inventory):
            raise ValueError("Unknown item owner")
        nums = [p.chapter_number for p in self.outline.chapters]
        if sorted(nums) != list(range(1, len(nums) + 1)):
            raise ValueError("Chapter plans must be contiguous and unique")
        for n in range(1, self.chapter_number + 1):
            if not any(p.chapter_number == n and p.chapter_actual_summary.strip()
                       for p in self.outline.chapters):
                raise ValueError("Committed chapter requires an actual summary")
        return self


class Review(Model):
    passed: bool
    feedback: list[str]


class Draft(Model):
    id: str
    chapter_number: int = Field(ge=1)
    base_revision: str
    status: Literal["draft", "approved"] = "draft"
    text: str = Field(min_length=1)
    review: Review
    attempts: int = Field(ge=1)
    planning_id: str | None = None
    selected_branch_id: str | None = None


class StateDelta(Model):
    # Upserts use complete entities; quantity=0 represents a consumed item.
    roles: list[Role]
    inventory: list[Item]
    maps: list[Place]
    lore: list[Lore]
    chapter_actual_summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def summary_not_blank(self):
        if not self.chapter_actual_summary.strip():
            raise ValueError("Actual chapter summary cannot be blank")
        return self


PlanningText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class CharacterImpact(Model):
    character_id: PlanningText
    description: PlanningText


class StoryBranch(Model):
    id: PlanningText
    chapter_number: int = Field(ge=1)
    strategy: Literal["progression", "escalation", "revelation"]
    title: PlanningText
    summary: PlanningText
    chapter_goal: PlanningText
    expected_events: list[PlanningText] = Field(min_length=1, max_length=12)
    character_impacts: list[CharacterImpact]
    world_impacts: list[PlanningText]
    hook: PlanningText
    risk: PlanningText


class BranchSet(Model):
    branches: list[StoryBranch] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def distinct(self):
        if {b.strategy for b in self.branches} != {"progression", "escalation", "revelation"}:
            raise ValueError("Exactly one progression, escalation and revelation is required")
        if len({b.id for b in self.branches}) != 3:
            raise ValueError("Branch IDs must be unique")
        if len({b.chapter_number for b in self.branches}) != 1:
            raise ValueError("All branches must belong to the same chapter")
        return self


class PlanningState(BranchSet):
    id: PlanningText
    chapter_number: int = Field(ge=1)
    base_revision: PlanningText
    generated_at: PlanningText
    selected_at: PlanningText | None = None
    selected_branch_id: PlanningText | None = None
    draft_id: PlanningText | None = None
    status: Literal["generated", "selected", "draft_generated", "approved"]

    @model_validator(mode="after")
    def lifecycle(self):
        if any(b.chapter_number != self.chapter_number for b in self.branches):
            raise ValueError("Planning chapter mismatch")
        if self.status == "generated":
            if self.selected_branch_id or self.selected_at or self.draft_id:
                raise ValueError("Unselected planning cannot contain selection or draft metadata")
        elif self.selected_branch_id not in {b.id for b in self.branches} or not self.selected_at:
            raise ValueError("Selected branch and selection timestamp are required")
        if (self.status in ("draft_generated", "approved")) != bool(self.draft_id):
            raise ValueError("Draft lifecycle metadata mismatch")
        return self
