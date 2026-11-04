from permitengine.reading.quotes import check_field, check_spectators

ATTACHMENTS = {"insurance.txt": "NAMED INSURED:   Marina Tri Club\nVENUE: South\n  Pier, Port Halden\nLimit $2,000,000"}


def field(value, quote):
    return {"name": "x", "value": value, "quote": quote}


def test_a_real_quote_stands():
    assert check_field(field("Marina Tri Club", "NAMED INSURED:   Marina Tri Club"), "insurance.txt", ATTACHMENTS) is None


def test_whitespace_differences_pass():
    assert check_field(field("South Pier", "VENUE: South Pier, Port Halden"), "insurance.txt", ATTACHMENTS) is None
    assert check_field(field("South  Pier", "VENUE:  South\nPier, Port Halden"), "insurance.txt", ATTACHMENTS) is None


def test_an_invented_quote_is_rejected():
    assert check_field(field("Nowhere", "VENUE: Nowhere"), "insurance.txt", ATTACHMENTS) == "quote_not_found"


def test_an_altered_quote_is_rejected():
    assert check_field(field("$3,000,000", "Limit $3,000,000"), "insurance.txt", ATTACHMENTS) == "quote_not_found"


def test_a_value_not_inside_its_quote_is_rejected():
    assert check_field(field("Other Club", "NAMED INSURED:   Marina Tri Club"), "insurance.txt", ATTACHMENTS) == "value_not_in_quote"


def test_form_and_cover_letter_are_barred_as_sources():
    both = {**ATTACHMENTS, "form.json": "Marina Tri Club", "cover_letter.txt": "Marina Tri Club"}
    for document in ("form", "form.json", "cover_letter", "cover_letter.txt", "Cover Letter", None):
        assert check_field(field("Marina Tri Club", "Marina Tri Club"), document, both) == "barred_source"


def test_an_unknown_document_is_rejected():
    assert check_field(field("x", "x"), "other.txt", ATTACHMENTS) == "unknown_document"


def test_an_empty_quote_or_value_is_rejected():
    assert check_field(field("", "Marina"), "insurance.txt", ATTACHMENTS) == "no_quote"
    assert check_field(field("Marina", ""), "insurance.txt", ATTACHMENTS) == "no_quote"


def test_spectators_must_be_quoted_from_the_description():
    form = {"description": "A race with about 1,200 spectators on the seafront."}
    assert check_spectators({"value": 1200, "quote": "about 1,200 spectators"}, form) == 1200
    assert check_spectators({"value": 1200, "quote": "about 900 spectators"}, form) is None
    assert check_spectators({"value": 5000, "quote": "about 1,200 spectators"}, form) is None
    assert check_spectators({"value": None, "quote": None}, form) is None
    assert check_spectators(None, form) is None
