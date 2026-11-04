"""The quote check. Whitespace-normalised match against the named attachment, each value inside its quote.

The form and the cover letter are never allowed sources, in code, whatever the model says.
"""
BARRED = {"form", "form.json", "cover_letter", "cover_letter.txt", "cover letter"}


def normalise(text) -> str:
    return " ".join(str(text).split())


def check_field(field: dict, document, attachments: dict) -> str | None:
    """None if the field stands, or the reason it counts as absent."""
    if document is None or str(document).strip().casefold() in BARRED:
        return "barred_source"
    if document not in attachments:
        return "unknown_document"
    quote, value = field.get("quote"), field.get("value")
    if not quote or value in (None, ""):
        return "no_quote"
    wanted = normalise(quote)
    if wanted not in normalise(attachments[document]):
        return "quote_not_found"
    if normalise(value) not in wanted:
        return "value_not_in_quote"
    return None


def check_spectators(extracted: dict | None, form: dict) -> int | None:
    """Expected spectators come from the form's description, as a number found inside a quote found there. Anything else is null."""
    if not extracted or extracted.get("value") is None or not extracted.get("quote"):
        return None
    quote = normalise(extracted["quote"])
    if quote not in normalise(form.get("description", "")):
        return None
    value = extracted["value"]
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if str(value) not in quote.replace(",", ""):
        return None
    return value
