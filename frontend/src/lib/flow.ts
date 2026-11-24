// Client-side mirror of the backend flow rules (app/services/conversations.py),
// used by the flow map and the "Test conversation" preview.

export const END = "__end__";
export const HANDOFF = "__handoff__";

export type Option = { id: string; title: string; value: string; max?: number; next?: string | null; reply?: string | null };
export type Question = { key: string; label: string; prompt: string; options: Option[] };
export type Flow = { name: string; intro_message: string; closing_message: string; questions: Question[]; rules: any };
export type Prop = { name: string; location?: string; price_min?: number | null; price_max?: number | null; possession?: string | null; brochure_url?: string | null };

export const TEMPLATE_BUTTONS = ["Yes, go ahead", "Not now", "Stop"];
export const NOT_NOW_REPLY = "No problem! We'll be here whenever you're ready. 🙂";
export const STOP_REPLY = "You have been unsubscribed and will not receive further messages from us.";
export const HANDOFF_REPLY = "Sure! A property advisor will get in touch with you shortly. 🙏";

const inr = (v: number) => (v >= 10_000_000 ? `₹${+(v / 10_000_000).toFixed(2)} Cr` : `₹${Math.round(v / 100_000)} Lakh`);

export function propertyDetails(p?: Prop | null): string {
  if (!p) return "";
  const lines: string[] = [];
  if (p.location) lines.push(`📍 ${p.location}`);
  if (p.price_min && p.price_max) lines.push(`💰 ${inr(p.price_min)} – ${inr(p.price_max)}`);
  else if (p.price_min) lines.push(`💰 From ${inr(p.price_min)}`);
  if (p.possession) lines.push(`🏗️ ${p.possession}`);
  return lines.join("\n");
}

export function fmt(text: string, p?: Prop | null, name = "Amit"): string {
  return (text || "")
    .split("{name}").join(name)
    .split("{property}").join(p?.name || "our projects")
    .split("{property_details}").join(propertyDetails(p))
    .split("{brochure}").join(p?.brochure_url ? `\n📄 Brochure: ${p.brochure_url}` : "")
    .split("{business}").join("our team");
}

/** Where an answer leads: a later question index, END or HANDOFF. */
export function nextIndex(qs: Question[], current: number, o: Option): number | string {
  if (o.next === END || o.next === HANDOFF) return o.next;
  if (o.next) {
    const i = qs.findIndex((q) => q.key === o.next);
    if (i > current) return i;
  }
  return current + 1;
}

export function targetLabel(qs: Question[], current: number, o: Option): { text: string; kind: "q" | "end" | "handoff" } {
  const n = nextIndex(qs, current, o);
  if (n === HANDOFF) return { text: "Hand to a person", kind: "handoff" };
  if (n === END || (n as number) >= qs.length) return { text: "Closing message", kind: "end" };
  return { text: `Q${(n as number) + 1} · ${qs[n as number].label}`, kind: "q" };
}

export function computePriority(flow: Flow, answers: Record<string, string>, priceMin?: number | null): "hot" | "warm" | "cold" {
  const r = flow.rules || {};
  const t = answers.timeline, n = answers.next_step;
  let p: "hot" | "warm" | "cold" =
    (r.hot?.timeline_in || []).includes(t) && (r.hot?.next_step_in || []).includes(n) ? "hot"
      : (r.warm?.timeline_in || []).includes(t) ? "warm" : "cold";
  if (r.budget_below_min_downgrade && priceMin) {
    const bq = flow.questions.find((q) => q.key === "budget");
    const opt = bq?.options.find((o) => String(o.value) === answers.budget);
    if (opt?.max && opt.max < priceMin) p = p === "hot" ? "warm" : "cold";
  }
  return p;
}

/** Which questions are reachable (so the map can flag dead branches). */
export function reachable(qs: Question[]): Set<number> {
  const seen = new Set<number>();
  const walk = (i: number) => {
    if (i >= qs.length || seen.has(i)) return;
    seen.add(i);
    qs[i].options.forEach((o) => { const n = nextIndex(qs, i, o); if (typeof n === "number") walk(n); });
  };
  walk(0);
  return seen;
}
