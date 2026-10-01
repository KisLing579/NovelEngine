"""Read-only dashboard projection and deterministic commit change summaries."""
from copy import deepcopy


def planning_for(bundle, number):
    return deepcopy(bundle.get("narrative_planning", {}).get(str(number)) or {
        "chapter_number": number, "status": "none", "branches": [],
        "id": None, "selected_branch_id": None, "selected_at": None, "generated_at": None,
        "draft_id": None, "base_revision": None})


def summarize_changes(before, after):
    changes = []
    for domain in ("roles", "inventory", "maps", "lore"):
        old = {entity["id"]: entity for entity in before[domain]}
        new = {entity["id"]: entity for entity in after[domain]}
        for entity_id in sorted(old.keys() | new.keys()):
            previous, current = old.get(entity_id), new.get(entity_id)
            name = (current or previous).get("name", entity_id)
            if previous is None or current is None:
                changes.append({"domain": domain, "entity_id": entity_id, "name": name,
                                "operation": "added" if previous is None else "removed",
                                "field": None, "before": previous, "after": current})
            else:
                for field in sorted(previous.keys() | current.keys()):
                    if previous.get(field) != current.get(field):
                        changes.append({"domain": domain, "entity_id": entity_id, "name": name,
                                        "operation": "updated", "field": field,
                                        "before": previous.get(field), "after": current.get(field)})
    return deepcopy(changes)


def build_dashboard(bundle, provider_info):
    result = {"initialized": bundle is not None, "provider": dict(provider_info),
              "project": None, "committed_state": None, "current_draft": None,
              "chapters": [], "snapshots": [], "latest_snapshot": None,
              "recent_state_changes": None, "current_planning": None}
    if bundle is None:
        return result
    world = bundle["world"]
    number = world["chapter_number"]
    draft = bundle["chapters"].get(str(number + 1))
    planning = planning_for(bundle, number + 1)
    result["current_planning"] = planning
    chapter_numbers = {p["chapter_number"] for p in world["outline"]["chapters"]}
    workflow = "reviewed" if draft and draft["review"]["passed"] else (
        "draft" if draft else "approved" if number else "ready")
    result.update(project={"name": None, "volume": None, "chapter_number": number,
                           "active_chapter_number": number + 1 if number + 1 in chapter_numbers else number,
                           "status": workflow, "can_plan": number + 1 in chapter_numbers,
                           "can_generate": number + 1 in chapter_numbers and
                           planning["status"] in ("selected", "draft_generated") and
                           planning["base_revision"] == bundle["revision"]},
                  committed_state=world, current_draft=draft)
    for plan in world["outline"]["chapters"]:
        n = plan["chapter_number"]
        record = bundle["chapters"].get(str(n))
        result["chapters"].append({**plan, "status": record["status"] if record else "not_generated",
                                   "is_current": n == result["project"]["active_chapter_number"],
                                   "is_committed_head": n == number,
                                   "review": record["review"] if record else None})
    result["chapters"].sort(key=lambda chapter: chapter["chapter_number"])
    for n in sorted(int(key) for key in bundle["snapshots"]):
        result["snapshots"].append({"name": f"state_{n}", "chapter_number": n,
                                    "created_at": bundle.get("snapshot_metadata", {}).get(str(n), {}).get("created_at"),
                                    "is_current": n == number})
    result["latest_snapshot"] = result["snapshots"][-1] if result["snapshots"] else None
    if number:
        log = bundle.get("change_logs", {}).get(str(number))
        if log is None:
            # Phase 1 data remains readable without migration or invented timestamps.
            before = bundle["snapshots"].get(str(number - 1))
            after = bundle["snapshots"].get(str(number))
            if before is not None and after is not None:
                log = {"chapter": number, "changes": summarize_changes(before, after)}
        result["recent_state_changes"] = log
    return deepcopy(result)
