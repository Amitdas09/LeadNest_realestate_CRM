from app.services.importer import map_header, parse_rows
from app.services.sheet_layout import LAYOUT, _reshape
from tests.helpers import HEADER, row


def test_reshape_keeps_every_lead_and_identity():
    rows = [HEADER, row("1"), ["", "", ""], row("2", phone="p:+919812345679", email="")]
    header, data, extras = _reshape(rows, drop_extra=False)
    assert header[:len(LAYOUT)] == [h for _, h, *_ in LAYOUT]
    assert len(data) == 2  # blank row dropped, both leads kept
    assert extras == ["when_do_you_plan_to_buy"]  # looking-for and budget now have their own columns
    assert data[0][header.index("Looking For")] == "3 BHK" and data[0][header.index("Budget")] == "80 lakh"
    # Same identity as before: lead id, form id and phone parse to the same values.
    _, before, _ = parse_rows(rows)
    _, after, _ = parse_rows([header, *data])
    assert [(p.dedupe_key, p.phone, p.values["external_form_id"]) for p in before] == \
           [(p.dedupe_key, p.phone, p.values["external_form_id"]) for p in after]
    assert data[0][header.index("Lead ID *")] == "1" and data[1][header.index("Phone Number *")] == "+919812345679"


def test_reshape_drop_extra_and_headers_still_map():
    header, data, extras = _reshape([HEADER, row("1")], drop_extra=True)
    assert extras == [] and len(header) == len(LAYOUT)
    m = map_header(header)
    for canon, *_ in LAYOUT:
        assert canon in m, canon


def test_form_answers_are_labelled():
    from app.services.importer import form_answers

    raw = {"Looking For": "2 BHK", "Budget": "50-80 lakh", "Preferred Location": "Patia",
           "Property Details": "East facing, 2 parkings", "City *": "Cuttack"}
    assert form_answers(raw) == [
        {"label": "Looking for", "value": "2 BHK"}, {"label": "Budget", "value": "50-80 lakh"},
        {"label": "Preferred location", "value": "Patia"}, {"label": "Details", "value": "East facing, 2 parkings"}]
