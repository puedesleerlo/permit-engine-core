"""What the project owner sees at the 5-case stop: verdicts and Jev's answers against the cards."""
import statistics
from pathlib import Path

from ..store.records import read_record
from ..workspace import Workspace
from .labels import load_cards

JEV_FACTS = ("traffic_plan_adequate", "crowd_plan_adequate", "medical_plan_adequate", "narrow_venue")
VERDICT_CARDS = {"police_escort_letter": "escort_evidence", "police_escort_email": "escort_evidence", "ambulance_agreement": "ambulance_evidence", "certificate_of_insurance": "insurance"}


def compare_with_cards(ws: Workspace, case_ids: list, folder: Path) -> dict:
    cards = load_cards(ws)
    rows = []
    jev = {question: {"true": [], "false": []} for question in JEV_FACTS}
    for case_id in case_ids:
        record = read_record(folder, case_id) or {}
        facts = cards[case_id]["facts"]
        verdicts = {v["evidence_type"]: v["verdict"] for v in ((record.get("judge") or {}).get("output") or {}).get("verdicts", [])}
        answers = (record.get("jev") or {}).get("answers") or {}
        for question, value in answers.items():
            if question in jev and question in facts:
                jev[question]["true" if facts[question] else "false"].append(value)
        rows.append({"case_id": case_id, "stopped": record.get("stopped"), "first_pass": (record.get("first_pass") or {}).get("status"), "judge": (record.get("judge") or {}).get("status"),
                     "jev": (record.get("jev") or {}).get("status"), "verdicts": verdicts, "cards": {card: facts.get(card) for card in sorted(set(VERDICT_CARDS.values()))}, "jev_answers": answers})

    def spread(values):
        return {"n": len(values), "mean": statistics.mean(values) if values else None, "stdev": statistics.pstdev(values) if len(values) > 1 else None}

    return {"cases": rows, "jev_against_cards": {q: {"when_true": spread(v["true"]), "when_false": spread(v["false"])} for q, v in jev.items()}}
