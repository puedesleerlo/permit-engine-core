"""The structured-output schemas. Also used to validate every answer, whichever provider gave it."""


def link_extract_schema(type_ids: list) -> dict:
    return {
        "type": "object", "additionalProperties": False, "required": ["evidence", "expected_spectators", "unmapped_documents"],
        "properties": {
            "evidence": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["evidence_type", "status", "document", "fields"],
                "properties": {
                    "evidence_type": {"type": "string", "enum": type_ids},
                    "status": {"type": "string", "enum": ["found", "absent"]},
                    "document": {"type": ["string", "null"]},
                    "fields": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["name", "value", "quote"],
                        "properties": {"name": {"type": "string"}, "value": {"type": "string"}, "quote": {"type": "string"}}}},
                }}},
            "expected_spectators": {
                "type": "object", "additionalProperties": False, "required": ["value", "quote"],
                "properties": {"value": {"type": ["integer", "null"]}, "quote": {"type": ["string", "null"]}}},
            "unmapped_documents": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["document", "why"],
                "properties": {"document": {"type": "string"}, "why": {"type": "string"}}}},
        },
    }


def judge_schema(type_ids: list) -> dict:
    return {
        "type": "object", "additionalProperties": False, "required": ["verdicts"],
        "properties": {"verdicts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["evidence_type", "verdict", "reason"],
            "properties": {
                "evidence_type": {"type": "string", "enum": type_ids},
                "verdict": {"type": "string", "enum": ["supported", "unsupported", "contradicted"]},
                "reason": {"type": ["string", "null"]},
            }}}},
    }


BASELINE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["ruling", "reason"],
    "properties": {"ruling": {"type": "string", "enum": ["approve", "deny"]}, "reason": {"type": "string"}},
}
