/**
 * LeadNest instant trigger for the "Property Leads" Google Sheet.
 *
 * The moment a lead row is complete (name, phone, email, city, WhatsApp consent), this tells
 * LeadNest to check the sheet now, so the WhatsApp flow starts within seconds instead of waiting
 * for the regular once-a-minute check. Nothing is sent while no new lead arrives.
 *
 * Setup (once): Extensions → Apps Script → paste this file → set LEADNEST_URL and TOKEN →
 * choose the function "setup" → Run → allow the permissions Google asks for.
 */
const LEADNEST_URL = "https://YOUR-DOMAIN/webhooks/sheet";
const TOKEN = "PASTE-THE-SHEET-TRIGGER-TOKEN";
const REQUIRED = ["Full Name *", "Phone Number *", "Email *", "City *", "WhatsApp Consent *", "Lead ID *"];

/** Run once: installs the triggers (safe to run again). */
function setup() {
  const ss = SpreadsheetApp.getActive();
  ScriptApp.getProjectTriggers().forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("onLeadEdit").forSpreadsheet(ss).onEdit().create();
  ScriptApp.newTrigger("onLeadChange").forSpreadsheet(ss).onChange().create();
  notify_(); // test call: LeadNest checks the sheet once now
}

/** A cell was typed or pasted: check that row. */
function onLeadEdit(e) {
  if (e && e.range && e.range.getSheet().getIndex() === 1) checkRow_(e.range.getSheet(), e.range.getLastRow());
}

/** Rows inserted / pasted / form submissions: check the last row. */
function onLeadChange() {
  const sheet = SpreadsheetApp.getActive().getSheets()[0];
  checkRow_(sheet, sheet.getLastRow());
}

function checkRow_(sheet, rowNumber) {
  if (rowNumber < 2) return;
  const width = sheet.getLastColumn();
  const header = sheet.getRange(1, 1, 1, width).getValues()[0].map(String);
  const row = sheet.getRange(rowNumber, 1, 1, width).getValues()[0];
  const complete = REQUIRED.every((h) => {
    const i = header.indexOf(h);
    return i >= 0 && String(row[i]).trim() !== "";
  });
  if (complete) notify_();
}

function notify_() {
  const res = UrlFetchApp.fetch(LEADNEST_URL, {
    method: "post",
    headers: { "X-LeadNest-Token": TOKEN },
    muteHttpExceptions: true,
  });
  console.log("LeadNest trigger: HTTP " + res.getResponseCode());
}
