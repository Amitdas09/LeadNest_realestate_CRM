const TZ = "Asia/Kolkata";

export function timeAgo(iso?: string | null): string {
  if (!iso) return "—";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 172800) return "Yesterday";
  return `${Math.round(s / 86400)} days ago`;
}

export function dateTime(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function clock(iso?: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-IN", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
}

export function dayLabel(iso: string): string {
  const d = new Date(iso);
  const fmt = (x: Date) => x.toLocaleDateString("en-IN", { timeZone: TZ });
  const today = new Date();
  const yest = new Date(Date.now() - 86400000);
  if (fmt(d) === fmt(today)) return "Today";
  if (fmt(d) === fmt(yest)) return "Yesterday";
  return d.toLocaleDateString("en-IN", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" });
}

export function inr(v?: number | null): string {
  if (v === null || v === undefined) return "—";
  if (v >= 10_000_000) return `₹${+(v / 10_000_000).toFixed(2)} Cr`;
  if (v >= 100_000) return `₹${+(v / 100_000).toFixed(1)} L`;
  return `₹${v.toLocaleString("en-IN")}`;
}

export const STATUS_LABEL: Record<string, string> = {
  new: "New", contacted: "Contacted", qualified: "Qualified", site_visit: "Site Visit",
  negotiation: "Negotiation", won: "Won", lost: "Lost", nurture: "Nurture",
};

export const ACTION_LABEL: Record<string, string> = {
  "lead.created": "Lead created",
  "lead.qualified": "Qualified on WhatsApp",
  "lead.status_change": "Status changed",
  "lead.owner_change": "Owner changed",
  "lead.priority_change": "Priority changed",
  "lead.note_added": "Internal note added",
  "lead.requirement_edit": "Requirement edited",
  "lead.phone_reveal": "Phone number revealed",
  "conversation.started": "WhatsApp opening message queued",
  "conversation.handoff": "Handed to a person",
  "conversation.takeover": "Agent took over",
  "conversation.resume_bot": "Returned to bot",
  "consent.opt_out": "Customer opted out (STOP)",
  "consent.change": "Consent changed",
  "message.agent_send": "Agent sent a message",
  "followup.created": "Follow-up scheduled",
  "followup.done": "Follow-up completed",
  "import.batch_completed": "Import finished",
};

export function humanize(s?: string | null): string {
  if (!s) return "";
  return s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
