from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SpecDiff:
    operations: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=lambda: {"added": 0, "removed": 0, "modified": 0})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _label_endpoint(ep: dict[str, Any]) -> str:
    return f"{ep['method']} {ep['path']}"


def diff_spec(old: dict[str, Any], new: dict[str, Any]) -> SpecDiff:
    ops: list[dict[str, Any]] = []

    if (old.get("app") or {}) != (new.get("app") or {}):
        ops.append(
            {
                "type": "modified",
                "kind": "app",
                "label": "app metadata",
                "before": old.get("app"),
                "after": new.get("app"),
            }
        )

    if (old.get("auth") or {}) != (new.get("auth") or {}):
        ops.append(
            {
                "type": "modified",
                "kind": "auth",
                "label": "auth",
                "before": old.get("auth"),
                "after": new.get("auth"),
            }
        )

    ops.extend(_collection_diff(old.get("entities", []), new.get("entities", []), "entity", lambda e: e["name"]))
    ops.extend(_collection_diff(old.get("endpoints", []), new.get("endpoints", []), "endpoint", _label_endpoint))
    ops.extend(_collection_diff(old.get("screens", []), new.get("screens", []), "screen", lambda s: s["name"]))

    summary = {"added": 0, "removed": 0, "modified": 0}
    for op in ops:
        if op["type"] in summary:
            summary[op["type"]] += 1
    return SpecDiff(operations=ops, summary=summary)


def _collection_diff(
    old_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    kind: str,
    key_fn,
) -> list[dict[str, Any]]:
    old_map: dict[str, dict[str, Any]] = {key_fn(item): item for item in old_items}
    new_map: dict[str, dict[str, Any]] = {key_fn(item): item for item in new_items}

    ops: list[dict[str, Any]] = []
    for label in sorted(new_map.keys() - old_map.keys()):
        ops.append({"type": "added", "kind": kind, "label": label, "after": new_map[label]})
    for label in sorted(old_map.keys() - new_map.keys()):
        ops.append({"type": "removed", "kind": kind, "label": label, "before": old_map[label]})
    for label in sorted(old_map.keys() & new_map.keys()):
        before = old_map[label]
        after = new_map[label]
        if before != after:
            ops.append(
                {
                    "type": "modified",
                    "kind": kind,
                    "label": label,
                    "before": before,
                    "after": after,
                }
            )
    return ops


def has_changes(diff: SpecDiff) -> bool:
    return bool(diff.operations)


__all__ = ["SpecDiff", "diff_spec", "has_changes"]
