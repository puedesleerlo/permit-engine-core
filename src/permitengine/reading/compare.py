"""Stage 5, in code: compare extracted fields with the form, for every evidence type, as the evidence map says.

`on_differ: field_mismatch` makes the record contradicted, whatever the verdict said. `on_differ: field_failed` fails the requirement.
A date that cannot be read counts as differing.
"""
import re
from datetime import date, datetime

_WEEKDAY = re.compile(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+")


def normalise(text) -> str:
    return " ".join(str(text).split()).casefold()


def parse_date(text, formats=("%d %B %Y", "%B %d, %Y", "%Y-%m-%d")) -> date | None:
    cleaned = _WEEKDAY.sub("", " ".join(str(text).split()).strip(" .,;"))
    for pattern in formats:
        try:
            return datetime.strptime(cleaned, pattern).date()
        except ValueError:
            continue
    return None


def matches(kind: str, value, form_value, formats) -> bool:
    if form_value is None:
        return False
    if kind == "same_text":
        return normalise(value) == normalise(form_value)
    if kind == "contains_form_value":
        return normalise(form_value) in normalise(value)
    day, form_day = parse_date(value, formats), parse_date(form_value, formats)
    if day is None or form_day is None:
        return False
    if kind == "same_date":
        return day == form_day
    if kind == "on_or_before_form_date":
        return day <= form_day
    if kind == "on_or_after_form_date":
        return day >= form_day
    raise ValueError(f"unknown comparison kind {kind}")


def compare_fields(rec: dict, definition: dict, form: dict, formats) -> None:
    """Sets field_failed, field_mismatch and each field's matches_form on the record. Fields that failed the quote check count as absent."""
    specs = {spec["name"]: spec.get("compare") for spec in definition.get("fields", [])}
    for field in rec["fields"]:
        rule = specs.get(field["name"])
        if not field.get("verified") or not rule:
            field["matches_form"] = None
            continue
        same = matches(rule["kind"], field["value"], form.get(rule["form_field"]), formats or ("%d %B %Y", "%B %d, %Y", "%Y-%m-%d"))
        field["matches_form"] = same
        if not same:
            rec[rule["on_differ"]] = True
            if rule["on_differ"] == "field_mismatch":
                rec["mismatch_reason"] = f"{field['name']} does not match {rule['form_field']} on the form"
