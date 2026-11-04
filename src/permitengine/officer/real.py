"""An LLM stands in for a person: it reads the case documents, the system's decision and the expert rubric."""
import json

from ..models.llm import LlmClient, ModelFailure
from ..trees.loader import LEVEL_NAMES, TREE_IDS
from ..workspace import EngineError, Workspace
from .base import Ruling

LABEL = "Simulated officer: an LLM following the expert rubric"
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["ruling", "outcome_risky", "reason", "named"],
    "properties": {
        "ruling": {"type": "string", "enum": ["approve", "deny"]},
        "outcome_risky": {"type": "boolean"},
        "reason": {"type": "string"},
        "named": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["tree_id", "level"],
            "properties": {"tree_id": {"type": "string", "enum": list(TREE_IDS)}, "level": {"type": "integer", "enum": [0, 1, 2]}}}},
    },
}


def read_rubric(ws: Workspace) -> str:
    path = ws.root / "generator" / "expert_rubric.md"
    if not path.exists():
        raise EngineError(f"{path} does not exist")
    return path.read_text(encoding="utf-8")


def trees_to_level(view: dict) -> list:
    """The trees whose hazard applies to this case. The officer gives a level for each, and every review teaches."""
    model = view.get("model")
    if model is None:
        return []
    return sorted(tree_id for tree_id, tree in model.trees.items() if view["applies"].get(tree.hazard))


class LlmOfficer:
    label = LABEL

    def __init__(self, ws: Workspace, client: LlmClient):
        prompt = (ws.rules / "prompts" / "officer.md").read_text(encoding="utf-8")
        self.system = prompt.replace("{{rubric}}", read_rubric(ws)).replace("{{levels}}", json.dumps(LEVEL_NAMES))
        self.client = client

    def rule(self, view: dict) -> Ruling:
        app = view["app"]
        case = {"documents": {"form": app.form, "cover_letter": app.cover_letter, "attachments": app.attachments},
                "system_decision": view["decision"], "risk": view["risk"], "hazards": view["hazard_summary"], "trees_to_level": trees_to_level(view)}
        user = json.dumps(case, indent=1, sort_keys=True, ensure_ascii=False)
        try:
            answer = self.client.structured("officer", self.system, user, SCHEMA, view["case_id"])
        except ModelFailure as exc:
            return Ruling(None, None, f"The LLM officer gave no usable ruling ({exc}).", [])
        wanted = set(case["trees_to_level"])
        return Ruling(answer["ruling"], answer["outcome_risky"], answer["reason"], [item for item in answer["named"] if item["tree_id"] in wanted])
