"""The evidence types a case needs: those named by requirements, and those named by evidence and jev questions in the trees."""


def needed_types(ctx) -> list:
    known = {t["id"] for t in ctx.evidence_map.get("evidence_types", [])}
    needed = set()
    for requirement in ctx.evidence_map.get("requirements", []):
        for key in ("evidence_type", "met_by"):
            value = requirement.get(key)
            if isinstance(value, str):
                needed.add(value)
            elif isinstance(value, list):
                needed.update(value)
    for tree in ctx.trees.values():
        for question in tree.questions:
            needed.update(question.get("evidence_types", []))
            needed.update(n for n in question.get("needs", []) if n in known)
    return sorted(needed & known)
