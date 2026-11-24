"""Give the lead sheet a clean, easy-to-read layout (and a "How it works" tab).

Every lead row is kept. Columns are re-ordered into the standard layout below, headers get
plain-English names and notes, required cells turn red when empty, and the consent column gets a
yes/no dropdown. Running it again is safe (idempotent). Needs Editor access for the service account.
"""

import re
from typing import Any

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from app.core.config import get_settings
from app.services.importer import FIELD_ALIASES, map_header, strip_prefix

API = "https://sheets.googleapis.com/v4/spreadsheets"
ROWS = 1000
GUIDE_TAB = "How it works"

# (canonical field, header text, group, width px, note). Groups: req = must be filled before the
# first WhatsApp message; prop = what the customer wants (optional); auto = filled by Meta.
LAYOUT: list[tuple[str, str, str, int, str]] = [
    ("created_time", "Submitted At", "auto", 175,
     "When the customer submitted the form. Filled automatically by Meta."),
    ("full_name", "Full Name *", "req", 170, "Customer's full name. Required."),
    ("phone", "Phone Number *", "req", 150,
     "WhatsApp number with country code, e.g. +91 98765 43210. Required."),
    ("email", "Email *", "req", 220, "Customer's email address. Required."),
    ("city", "City *", "req", 125, "City the customer lives in. Required."),
    ("consent", "WhatsApp Consent *", "req", 150,
     "yes = the customer agreed to be contacted on WhatsApp. Anything else means no message is sent."),
    ("form_name", "Property", "prop", 210, "The property this enquiry is for (the lead form name)."),
    ("interest", "Looking For", "prop", 190,
     "Pick from the list (1 BHK … Office space). Decides which WhatsApp questions the customer gets."),
    ("budget", "Budget", "prop", 170, "Pick a budget range from the list."),
    ("preferred_location", "Preferred Location", "prop", 170,
     "Area or locality the customer prefers, e.g. Patia, Bhubaneswar."),
    ("details", "Property Details", "prop", 300,
     "Anything else the customer asked for: floor, facing, parking, possession, loan help…"),
    ("campaign_name", "Campaign", "auto", 170, "Ad campaign (filled automatically by Meta)."),
    ("ad_name", "Ad Name", "auto", 130, "Ad that brought the lead (filled automatically by Meta)."),
    ("platform", "Platform", "auto", 95, "fb = Facebook, ig = Instagram (filled automatically by Meta)."),
    ("external_form_id", "Form ID", "auto", 130,
     "Meta lead form ID. Links the lead to its property and WhatsApp questions in LeadNest."),
    ("external_lead_id", "Lead ID *", "req", 140,
     "Required, and fill it LAST. A row is only taken once its Lead ID is entered, so a half-typed or copied "
     "row is never messaged with the wrong details. Meta fills it automatically; for a manual entry type any "
     "new number (e.g. 1124000720)."),
]
# Fixed choices (dropdowns). Only these values can be typed or picked, so every lead is clean and the
# CRM can pick the right WhatsApp questions ("Looking For" -> apartment / plot / commercial flow).
OPTIONS: dict[str, list[str]] = {
    "interest": ["1 BHK", "2 BHK", "3 BHK", "4 BHK or bigger", "Villa / Independent house", "Residential plot",
                 "Commercial plot", "Office space", "Retail shop / Showroom", "Warehouse"],
    "budget": ["Under ₹30 Lakh", "₹30–50 Lakh", "₹50–80 Lakh", "₹80 Lakh–1.2 Cr", "₹1.2–2 Cr", "Above ₹2 Cr",
               "Rent: under ₹30K / month", "Rent: ₹30K+ / month"],
    "consent": ["yes", "no"],
    "platform": ["fb", "ig", "website", "walk-in", "manual"],
}
HEAD_STYLE = {"req": ("#0D8442", "#FFFFFF"), "prop": ("#D7EEDF", "#0B2A20"), "auto": ("#E7ECEA", "#475569")}

GREEN, GREEN_DARK, INK, MUTED = "#0D8442", "#0B2A20", "#1F2937", "#475569"
BAND, RED_SOFT, GREEN_SOFT, AMBER_SOFT = "#F6F9F7", "#FDE8E8", "#E3F5EA", "#FFF4DB"


def _rgb(hex_color: str) -> dict[str, Any]:
    h = hex_color.lstrip("#")
    return {"rgbColor": {k: int(h[i:i + 2], 16) / 255 for k, i in (("red", 0), ("green", 2), ("blue", 4))}}


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _session() -> AuthorizedSession:
    creds = service_account.Credentials.from_service_account_file(
        str(get_settings().google_key_path), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return AuthorizedSession(creds)


def _check(r) -> dict[str, Any]:
    if not r.ok:
        raise RuntimeError(f"Google Sheets error HTTP {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else {}


def _reshape(rows: list[list[str]], drop_extra: bool) -> tuple[list[str], list[list[str]], list[str]]:
    """Return (header, data rows, extra header names kept) in the standard layout."""
    if not rows:
        return [h for _, h, *_ in LAYOUT], [], []
    old_header = rows[0]
    mapping = map_header(old_header)
    used = {mapping[c] for c, *_ in LAYOUT if c in mapping}
    extra_idx = [] if drop_extra else [
        i for i, h in enumerate(old_header) if i not in used and str(h).strip()
        and any(i < len(r) and str(r[i]).strip() for r in rows[1:])]
    header = [h for _, h, *_ in LAYOUT] + [str(old_header[i]) for i in extra_idx]
    data = []
    for r in rows[1:]:
        if not any(str(c).strip() for c in r):
            continue
        cell = lambda i: str(r[i]) if i is not None and i < len(r) else ""  # noqa: E731
        out = []
        for canon, *_ in LAYOUT:
            v = cell(mapping.get(canon))
            if canon in ("external_lead_id", "external_form_id"):
                v = strip_prefix(v)  # "l:123" / "f:456" -> plain id (same identity in the CRM)
            elif canon == "phone":
                v = re.sub(r"^p:", "", v.strip())
            out.append(v)
        data.append(out + [cell(i) for i in extra_idx])
    return header, data, [str(old_header[i]) for i in extra_idx]


def _guide_rows() -> list[list[str]]:
    rows = [
        ["Property Leads"],
        ["How this sheet works with LeadNest"],
        [""],
        ["What happens to a new row"],
        ["Step 1", "", "A new enquiry arrives as a new row in the Leads tab (from Meta lead ads, or typed in by hand)."],
        ["Step 2", "", "Typing a row by hand? Fill every other cell first and the Lead ID LAST. Until the Lead ID "
                       "is entered, LeadNest ignores the row, so nothing is sent while you are still typing."],
        ["Step 3", "", "As soon as the Lead ID is filled, every column marked * is filled and WhatsApp Consent is "
                       "\"yes\", the customer gets a WhatsApp message within seconds, built from what the row says."],
        ["Step 4", "", "If something is missing, the empty cell turns red and no message is sent. Fill it in: "
                       "LeadNest notices on its next check and sends the message automatically."],
        [""],
        ["Columns", "Required", "What goes here"],
    ]
    rows += [[h.rstrip(" *"), "Yes" if grp == "req" else "No", note] for _, h, grp, _, note in LAYOUT]
    rows += [
        [""],
        ["Good to know"],
        ["Header row", "", "Don't rename, move or delete it: LeadNest finds each column by its name."],
        ["Duplicates", "", "One row = one enquiry, identified by its Lead ID. Re-saving or sorting rows never "
                           "creates duplicate leads or extra messages. Copying a row? Give the copy a NEW Lead ID."],
        ["Property wishes", "", "Property, Looking For, Budget, Preferred Location and Property Details come "
                                "straight into the first WhatsApp message and the CRM. Looking For decides the "
                                "questions: BHK / villa = home questions, plot = plot questions, office / shop / "
                                "warehouse = commercial questions."],
        ["Dropdowns", "", "Looking For, Budget, WhatsApp Consent and Platform only accept the values in their "
                          "dropdown (click the cell, then the small arrow)."],
        ["Colours", "", "Dark green header = required. Light green = property wishes. Grey = filled by Meta. "
                        "Red cell = required detail missing. Green consent = can be messaged. "
                        "Amber consent = no consent, so no message."],
    ]
    return rows


def apply_layout(sheet_id: str | None = None, *, drop_extra: bool = False) -> dict[str, Any]:
    s = _session()
    settings = get_settings()
    sheet_id = sheet_id or settings.google_sheet_id
    meta = _check(s.get(f"{API}/{sheet_id}", params={
        "fields": "sheets(properties(sheetId,title,index),bandedRanges(bandedRangeId),"
                  "conditionalFormats,protectedRanges(protectedRangeId))"}))
    sheets_ = sorted(meta["sheets"], key=lambda x: x["properties"]["index"])
    first = sheets_[0]
    sid, title = first["properties"]["sheetId"], first["properties"]["title"]
    rows = _check(s.get(f"{API}/{sheet_id}/values/'{title}'",
                        params={"valueRenderOption": "FORMATTED_VALUE"})).get("values", [])
    header, data, extras = _reshape(rows, drop_extra)
    ncols = len(header)
    nrows = max(ROWS, len(data) + 50)
    req_cols = [i for i, (_, _, grp, _, _) in enumerate(LAYOUT) if grp == "req"]
    consent_col = next(i for i, (c, *_) in enumerate(LAYOUT) if c == "consent")
    phone_col = next(i for i, (c, *_) in enumerate(LAYOUT) if c == "phone")
    last = _col(ncols - 1)

    reqs: list[dict[str, Any]] = []
    reqs += [{"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}} for b in first.get("bandedRanges", [])]
    reqs += [{"deleteProtectedRange": {"protectedRangeId": p["protectedRangeId"]}}
             for p in first.get("protectedRanges", [])]
    reqs += [{"deleteConditionalFormatRule": {"sheetId": sid, "index": 0}}
             for _ in first.get("conditionalFormats", [])]
    reqs.append({"updateCells": {"range": {"sheetId": sid}, "fields": "userEnteredFormat,note,dataValidation"}})
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sid, "title": "Leads", "tabColorStyle": _rgb(GREEN),
                       "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 2, "hideGridlines": True,
                                          "rowCount": nrows, "columnCount": ncols}},
        "fields": "title,tabColorStyle,gridProperties(frozenRowCount,frozenColumnCount,hideGridlines,"
                  "rowCount,columnCount)"}})
    # Body: comfortable rows, vertically centred text, phone kept as text.
    reqs.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": nrows, "startColumnIndex": 0, "endColumnIndex": ncols},
        "cell": {"userEnteredFormat": {"verticalAlignment": "MIDDLE", "wrapStrategy": "CLIP",
                                       "padding": {"left": 8, "right": 8},
                                       "textFormat": {"fontSize": 10, "foregroundColorStyle": _rgb(INK)}}},
        "fields": "userEnteredFormat(verticalAlignment,wrapStrategy,padding,textFormat)"}})
    reqs.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": nrows, "startColumnIndex": phone_col, "endColumnIndex": phone_col + 1},
        "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
        "fields": "userEnteredFormat.numberFormat"}})
    # Header: green = required, light green = property wishes, grey = filled automatically by Meta.
    head_cells = []
    for i in range(ncols):
        bg, fg = HEAD_STYLE[LAYOUT[i][2] if i < len(LAYOUT) else "auto"]
        note = LAYOUT[i][4] if i < len(LAYOUT) else "Extra column kept from the original sheet."
        head_cells.append({"note": note, "userEnteredFormat": {
            "backgroundColorStyle": _rgb(bg),
            "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP", "padding": {"left": 8, "right": 8},
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColorStyle": _rgb(fg)},
            "borders": {"bottom": {"style": "SOLID_MEDIUM", "colorStyle": _rgb(GREEN_DARK)}}}})
    reqs.append({"updateCells": {"rows": [{"values": head_cells}], "fields": "note,userEnteredFormat",
                                 "start": {"sheetId": sid, "rowIndex": 0, "columnIndex": 0}}})
    reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0,
                                                         "endIndex": 1},
                                               "properties": {"pixelSize": 44}, "fields": "pixelSize"}})
    reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 1,
                                                         "endIndex": nrows},
                                               "properties": {"pixelSize": 30}, "fields": "pixelSize"}})
    for i in range(ncols):
        width = LAYOUT[i][3] if i < len(LAYOUT) else 160
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize"}})
    reqs.append({"addBanding": {"bandedRange": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": nrows, "startColumnIndex": 0, "endColumnIndex": ncols},
        "rowProperties": {"firstBandColorStyle": _rgb("#FFFFFF"), "secondBandColorStyle": _rgb(BAND)}}}})
    # Dropdowns with fixed choices; anything else is rejected when typed in the sheet.
    for i, (canon, *_) in enumerate(LAYOUT):
        if canon in OPTIONS:
            reqs.append({"setDataValidation": {
                "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": nrows,
                          "startColumnIndex": i, "endColumnIndex": i + 1},
                "rule": {"condition": {"type": "ONE_OF_LIST",
                                       "values": [{"userEnteredValue": o} for o in OPTIONS[canon]]},
                         "inputMessage": "Pick one of the options from the list.",
                         "strict": True, "showCustomUi": True}}})
    c = _col(consent_col)
    yes_re = "^(" + "|".join(sorted({"yes", "y", "true", "1", "agree", "agreed", "i agree", "opted in"})) + ")$"
    rules = [
        # Required cell empty on a row that has data -> red.
        ({"ranges": [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": nrows, "startColumnIndex": i, "endColumnIndex": i + 1}
                     for i in req_cols],
          "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [
              {"userEnteredValue": f'=AND(COUNTA($A2:${last}2)>0,LEN(TRIM(INDIRECT("RC",FALSE)))=0)'}]},
              "format": {"backgroundColorStyle": _rgb(RED_SOFT)}}}),
        ({"ranges": [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": nrows, "startColumnIndex": consent_col,
                      "endColumnIndex": consent_col + 1}],
          "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [
              {"userEnteredValue": f'=REGEXMATCH(LOWER(TRIM(${c}2)),"{yes_re}")'}]},
              "format": {"backgroundColorStyle": _rgb(GREEN_SOFT),
                         "textFormat": {"bold": True, "foregroundColorStyle": _rgb(GREEN)}}}}),
        ({"ranges": [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": nrows, "startColumnIndex": consent_col,
                      "endColumnIndex": consent_col + 1}],
          "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [
              {"userEnteredValue": f'=LEN(TRIM(${c}2))>0'}]},
              "format": {"backgroundColorStyle": _rgb(AMBER_SOFT)}}}),
    ]
    reqs += [{"addConditionalFormatRule": {"rule": r, "index": n}} for n, r in enumerate(rules)]
    reqs.append({"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
        "description": "Header row: LeadNest finds columns by these names", "warningOnly": True}}})

    # Guide tab: recreate it so the text is always current.
    for sh in sheets_[1:]:
        if sh["properties"]["title"] == GUIDE_TAB:
            reqs.append({"deleteSheet": {"sheetId": sh["properties"]["sheetId"]}})
    reqs.append({"addSheet": {"properties": {"title": GUIDE_TAB, "index": 1, "tabColorStyle": _rgb(GREEN_DARK),
                                             "gridProperties": {"hideGridlines": True, "rowCount": 60,
                                                                "columnCount": 3}}}})

    # 1) clear old values, 2) restyle, 3) write the reshaped rows (RAW keeps "+91..." as text).
    _check(s.post(f"{API}/{sheet_id}/values/'{title}':clear"))
    reply = _check(s.post(f"{API}/{sheet_id}:batchUpdate", json={"requests": reqs}))
    _check(s.put(f"{API}/{sheet_id}/values/'Leads'!A1", params={"valueInputOption": "RAW"},
                 json={"values": [header, *data]}))

    guide_id = next(r["addSheet"]["properties"]["sheetId"] for r in reply.get("replies", []) if "addSheet" in r)
    guide = _guide_rows()
    _check(s.put(f"{API}/{sheet_id}/values/'{GUIDE_TAB}'!A1", params={"valueInputOption": "RAW"},
                 json={"values": guide}))
    table_start = next(i for i, r in enumerate(guide) if r and r[0] == "Columns")
    g = [
        {"updateDimensionProperties": {"range": {"sheetId": guide_id, "dimension": "COLUMNS", "startIndex": i,
                                                 "endIndex": i + 1},
                                       "properties": {"pixelSize": w}, "fields": "pixelSize"}}
        for i, w in enumerate((190, 95, 620))
    ]
    g.append({"repeatCell": {"range": {"sheetId": guide_id}, "cell": {"userEnteredFormat": {
        "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE", "padding": {"left": 8, "right": 8, "top": 4, "bottom": 4},
        "textFormat": {"fontSize": 10, "foregroundColorStyle": _rgb(INK)}}},
        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment,padding,textFormat)"}})
    g.append({"repeatCell": {"range": {"sheetId": guide_id, "startRowIndex": 0, "endRowIndex": 1},
                             "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 16,
                                                                           "foregroundColorStyle": _rgb(GREEN_DARK)}}},
                             "fields": "userEnteredFormat.textFormat"}})
    g.append({"repeatCell": {"range": {"sheetId": guide_id, "startRowIndex": 1, "endRowIndex": 2},
                             "cell": {"userEnteredFormat": {"textFormat": {"fontSize": 11,
                                                                           "foregroundColorStyle": _rgb(MUTED)}}},
                             "fields": "userEnteredFormat.textFormat"}})
    for i, r in enumerate(guide):
        if len(r) == 1 and r[0] and i > 1:  # section titles
            g.append({"repeatCell": {"range": {"sheetId": guide_id, "startRowIndex": i, "endRowIndex": i + 1},
                                     "cell": {"userEnteredFormat": {"textFormat": {
                                         "bold": True, "fontSize": 12, "foregroundColorStyle": _rgb(GREEN)}}},
                                     "fields": "userEnteredFormat.textFormat"}})
    g.append({"repeatCell": {"range": {"sheetId": guide_id, "startRowIndex": table_start,
                                       "endRowIndex": table_start + 1},
                             "cell": {"userEnteredFormat": {"backgroundColorStyle": _rgb(GREEN), "textFormat": {
                                 "bold": True, "foregroundColorStyle": _rgb("#FFFFFF")}}},
                             "fields": "userEnteredFormat(backgroundColorStyle,textFormat)"}})
    g.append({"addBanding": {"bandedRange": {
        "range": {"sheetId": guide_id, "startRowIndex": table_start + 1, "endRowIndex": table_start + 1 + len(LAYOUT),
                  "startColumnIndex": 0, "endColumnIndex": 3},
        "rowProperties": {"firstBandColorStyle": _rgb("#FFFFFF"), "secondBandColorStyle": _rgb(BAND)}}}})
    _check(s.post(f"{API}/{sheet_id}:batchUpdate", json={"requests": g}))
    return {"rows": len(data), "columns": header, "extra_columns_kept": extras,
            "known_fields": sorted(FIELD_ALIASES)}
