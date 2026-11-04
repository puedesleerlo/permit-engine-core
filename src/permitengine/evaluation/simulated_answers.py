"""Simulated answers, from cards, with noise like experiments/sim_data_plan.py. No model is called. Every record says `source: simulated`.

The flow is the real one in reading/read.py, so simulated records take the same path through quote check, comparison and Rego.
Linking goes by file name and fields by labelled lines, which only works on generated documents. That is fine: this stands in for a reader.
"""
import random
import re

from ..pipeline.case import load_context
from ..reading.compare import parse_date
from ..reading.read import read_case
from ..store.records import records_dir, write_record
from ..workspace import Workspace
from .labels import load_cards

FACT_OK = 0.92  # chance the verdict on a tree's evidence is right, as in sim_data_plan.py
REQUIREMENT_OK = 0.98  # the plan has no noise figure for requirements; a clear certificate is rarely misread
JEV_TRUE, JEV_FALSE = (6, 1.5), (1.5, 6)
MODELS = {"llm": "simulated", "jev": "simulated"}
FILES = {"police_escort_letter": "police_letter.txt", "police_escort_email": "police_email.txt", "ambulance_agreement": "ambulance_agreement.txt",
         "certificate_of_insurance": "insurance.txt", "traffic_plan": "traffic_plan.txt", "crowd_plan": "crowd_plan.txt", "medical_plan": "medical_plan.txt", "race_plan": "race_plan.txt"}
DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2} [A-Z][a-z]+ \d{4}|[A-Z][a-z]+ \d{1,2}, \d{4}")
LABELS = {
    "named_insured": r"(?:NAMED INSURED:|Insured:|INSURED \.+|Who is covered:)\s*(.+)",
    "venue": r"(?:VENUE:|Location of event:|RISK LOCATION \.+|Where you are covered:)\s*(.+?)(?:, Port Halden| only)?\s*$",
    "coverage": r"(\$[\d,]+)",
    "signed_by": r"((?:Sgt\.|Sergeant|Insp\.|Inspector|Deputy Chief) [A-Z][\w'-]+(?: [A-Z][\w'-]+)*)",
    "sender": r"From:\s*(.+)",
    "provider": r"(?:Between:|Provider:)\s*([^(\n]+?)\s*(?:\(|$)",
}


def _line_with(text: str, value: str) -> str | None:
    for line in text.splitlines():
        if value in line:
            return line.strip()
    return None


def _labelled(text: str, name: str) -> tuple:
    pattern = LABELS.get(name)
    if pattern is None:
        return None, None
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None, None
    return match.group(1).strip(), _line_with(text, match.group(0).strip()) or match.group(0).strip()


def _period(text: str) -> list:
    """The certificate's dates in order, leaving out the date it was issued."""
    found = []
    for line in text.splitlines():
        if "issued" in line.casefold():
            continue
        found += [(value, line.strip()) for value in DATE.findall(line)]
    return found


def _event_day_on_document(text: str, form: dict) -> tuple:
    """The date this document is about: the event's own if it names it, otherwise the nearest other date, as a letter naming another date would."""
    event = parse_date(form.get("event_date") or "")
    best = None
    for line in text.splitlines():
        for value in DATE.findall(line):
            day = parse_date(value)
            if day is None or event is None:
                continue
            gap = abs((day - event).days)
            if best is None or gap < best[0]:
                best = (gap, value, line.strip())
    return (best[1], best[2]) if best else (None, None)


def _field(name: str, value, quote) -> dict | None:
    return {"name": name, "value": value, "quote": quote} if value and quote else None


def _extract(definition: dict, text: str, form: dict) -> list:
    rows = []
    period = _period(text) if definition["id"] == "certificate_of_insurance" else []
    for spec in definition.get("fields", []):
        name = spec["name"]
        if name == "event_date":
            value, quote = _event_day_on_document(text, form)
        elif name == "start_date" and period:
            value, quote = period[0]
        elif name == "end_date" and len(period) > 1:
            value, quote = period[1]
        elif name == "named_insured" and form.get("organizer") and form["organizer"] in text:
            value, quote = form["organizer"], _line_with(text, form["organizer"])
        else:
            value, quote = _labelled(text, name)
        row = _field(name, value, quote)
        if row:
            rows.append(row)
    return rows


class SimulatedReader:
    source = "simulated"
    models = MODELS

    def __init__(self, cards: dict, seed: int):
        self.cards = cards
        self.seed = seed

    def _rng(self, case_id: str, part: str) -> random.Random:
        return random.Random(f"{self.seed}:{case_id}:{part}")

    def link_extract(self, app, types: list) -> dict:
        facts = self.cards[app.case_id]["facts"]
        evidence, mapped = [], set()
        for definition in types:
            name = FILES.get(definition["id"])
            is_broker = definition["id"] == "certificate_of_insurance" and facts.get("insurance") == "broker_letter"
            if name in app.attachments and not is_broker:
                mapped.add(name)
                evidence.append({"evidence_type": definition["id"], "status": "found", "document": name, "fields": _extract(definition, app.attachments[name], app.form)})
            else:
                evidence.append({"evidence_type": definition["id"], "status": "absent", "document": None, "fields": []})
        unmapped = [{"document": name, "why": "It fits none of the evidence types asked for."} for name in sorted(app.attachments) if name not in mapped]
        return {"evidence": evidence, "expected_spectators": self._spectators(app, facts), "unmapped_documents": unmapped}

    @staticmethod
    def _spectators(app, facts: dict) -> dict:
        number = facts.get("spectators_mentioned")
        description = app.form.get("description", "")
        if not number or str(number) not in description:
            return {"value": None, "quote": None}
        sentence = next((s for s in re.split(r"(?<=[.!?])\s+", description) if str(number) in s), None)
        return {"value": number, "quote": sentence}

    def _truth(self, type_id: str, facts: dict) -> tuple:
        """The verdict an accurate reader gives, and how often this simulated one gives it."""
        if type_id in ("police_escort_letter", "police_escort_email"):
            return facts.get("escort_arranged") or facts.get("escort_evidence") == "contradicting", FACT_OK
        if type_id == "ambulance_agreement":
            return facts.get("ambulance_arranged"), FACT_OK
        if type_id == "certificate_of_insurance":
            return facts.get("insurance") == "valid", REQUIREMENT_OK
        return True, REQUIREMENT_OK

    def judge(self, app, items: list, typed: dict) -> dict:
        facts = self.cards[app.case_id]["facts"]
        rng = self._rng(app.case_id, "judge")
        verdicts = []
        for item in items:
            supported, accuracy = self._truth(item["evidence_type"], facts)
            said = supported if rng.random() < accuracy else not supported
            verdicts.append({"evidence_type": item["evidence_type"], "verdict": "supported" if said else "unsupported", "reason": None if said else "The passages do not establish this."})
        return {"verdicts": verdicts}

    def jev(self, app, state: dict, questions: dict) -> dict:
        facts = self.cards[app.case_id]["facts"]
        rng = self._rng(app.case_id, "jev")
        answers = {}
        for question_id in sorted(questions):
            a, b = JEV_TRUE if facts.get(question_id) else JEV_FALSE
            answers[question_id] = rng.betavariate(a, b)
        return answers


def simulate(ws: Workspace, seed: int = 7, splits=("train", "validation")) -> dict:
    """Writes simulated records. The test split is left out: its one look must be on real answers."""
    ctx = load_context(ws)
    reader = SimulatedReader(load_cards(ws), seed)
    folder = records_dir(ws, "simulated")
    all_splits = ws.splits()
    written = 0
    for split in splits:
        for case_id in all_splits[split]:
            write_record(folder, read_case(ws.application(case_id), reader, ctx))
            written += 1
    return {"source": "simulated", "written": written, "folder": str(folder), "splits": list(splits)}
