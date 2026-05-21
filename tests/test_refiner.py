import copy
import json
from pathlib import Path

from packages.refiner import diff_spec, has_changes

FIXTURES = Path(__file__).parent / "fixtures"


def _load_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def test_diff_spec_identical_returns_no_operations():
    spec = _load_spec()
    diff = diff_spec(spec, copy.deepcopy(spec))
    assert diff.operations == []
    assert diff.summary == {"added": 0, "removed": 0, "modified": 0}
    assert has_changes(diff) is False


def test_diff_spec_added_entity():
    old = _load_spec()
    new = copy.deepcopy(old)
    new["entities"].append({"name": "Tag", "fields": [{"name": "name", "type": "string"}]})
    diff = diff_spec(old, new)
    added = [op for op in diff.operations if op["type"] == "added"]
    assert len(added) == 1
    assert added[0]["kind"] == "entity"
    assert added[0]["label"] == "Tag"
    assert added[0]["after"]["name"] == "Tag"
    assert diff.summary["added"] == 1


def test_diff_spec_removed_endpoint():
    old = _load_spec()
    new = copy.deepcopy(old)
    new["endpoints"] = [ep for ep in new["endpoints"] if ep["path"] != "/todos/{id}" or ep["method"] != "DELETE"]
    diff = diff_spec(old, new)
    removed = [op for op in diff.operations if op["type"] == "removed"]
    assert len(removed) == 1
    assert removed[0]["kind"] == "endpoint"
    assert removed[0]["label"] == "DELETE /todos/{id}"
    assert diff.summary["removed"] == 1


def test_diff_spec_modified_entity_when_field_changes():
    old = _load_spec()
    new = copy.deepcopy(old)
    new["entities"][1]["fields"].append({"name": "priority", "type": "string", "required": False})
    diff = diff_spec(old, new)
    modified = [op for op in diff.operations if op["type"] == "modified" and op["kind"] == "entity"]
    assert len(modified) == 1
    assert modified[0]["label"] == "Todo"
    assert modified[0]["before"] != modified[0]["after"]
    assert diff.summary["modified"] == 1


def test_diff_spec_modified_screen_when_actions_change():
    old = _load_spec()
    new = copy.deepcopy(old)
    new["screens"][2]["actions"].append("filterTodos")
    diff = diff_spec(old, new)
    modified = [op for op in diff.operations if op["kind"] == "screen" and op["type"] == "modified"]
    assert len(modified) == 1
    assert modified[0]["label"] == "Todos"


def test_diff_spec_app_metadata_change_is_modified():
    old = _load_spec()
    new = copy.deepcopy(old)
    new["app"]["version"] = "0.2.0"
    diff = diff_spec(old, new)
    assert any(op["kind"] == "app" and op["type"] == "modified" for op in diff.operations)
    assert diff.summary["modified"] == 1


def test_diff_spec_to_dict_is_json_serializable():
    old = _load_spec()
    new = copy.deepcopy(old)
    new["entities"].append({"name": "Tag", "fields": [{"name": "name", "type": "string"}]})
    diff = diff_spec(old, new)
    serialised = json.dumps(diff.to_dict())
    decoded = json.loads(serialised)
    assert decoded["summary"]["added"] == 1
    assert decoded["operations"][0]["label"] == "Tag"
