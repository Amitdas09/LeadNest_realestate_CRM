import clsx from "clsx";
import { ArrowRight, Ban, Building2, CheckCircle2, FileSpreadsheet, MessageSquareReply, PauseCircle, Send, UserRound } from "lucide-react";
import { ReactNode } from "react";
import { Flow, fmt, HANDOFF_REPLY, NOT_NOW_REPLY, Prop, reachable, STOP_REPLY, targetLabel, TEMPLATE_BUTTONS } from "../lib/flow";

function Target({ kind, text }: { kind: string; text: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold",
      kind === "q" && "bg-teal-50 text-teal-700", kind === "end" && "bg-emerald-50 text-emerald-700",
      kind === "handoff" && "bg-violet-50 text-violet-700", kind === "nurture" && "bg-orange-50 text-orange-700",
      kind === "stop" && "bg-red-50 text-red-700")}>
      <ArrowRight className="h-3 w-3" /> {text}
    </span>
  );
}

function Node({ n, title, subtitle, tone = "teal", children }: { n?: ReactNode; title: string; subtitle?: string; tone?: string; children?: ReactNode }) {
  return (
    <div className={clsx("rounded-xl border bg-white", tone === "navy" ? "border-navy/30" : tone === "green" ? "border-emerald-300" : "border-slate-200")}>
      <div className="flex items-start gap-2 px-3 pt-2.5">
        {n !== undefined && <span className={clsx("mt-0.5 flex h-6 min-w-6 items-center justify-center rounded-full px-1.5 text-[11px] font-bold text-white", tone === "navy" ? "bg-navy" : tone === "green" ? "bg-emerald-600" : "bg-teal")}>{n}</span>}
        <div className="min-w-0">
          <div className="text-[13px] font-semibold text-navy">{title}</div>
          {subtitle && <div className="whitespace-pre-wrap text-[11px] text-slate-500">{subtitle}</div>}
        </div>
      </div>
      <div className="px-3 pb-2.5 pt-1.5">{children}</div>
    </div>
  );
}

const Down = () => <div className="ml-5 h-3 w-px bg-slate-300" />;

export default function FlowMap({ flow, prop }: { flow: Flow; prop?: Prop | null }) {
  const qs = flow.questions;
  const live = reachable(qs);
  return (
    <div className="space-y-0">
      <Node n={<FileSpreadsheet className="h-3.5 w-3.5" />} tone="navy" title="New row in the Google Sheet"
        subtitle="Checked every 60 s. Needs WhatsApp consent + a mapped form, otherwise saved in the CRM without messaging." />
      <Down />
      <Node n={<Send className="h-3 w-3" />} tone="navy" title="Opening WhatsApp message (approved template)"
        subtitle={`Hi Amit, thank you for your enquiry about ${prop?.name || "{property}"}! 🏡 …`}>
        <div className="space-y-1">
          {TEMPLATE_BUTTONS.map((b) => (
            <div key={b} className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-2 py-1 text-xs">
              <span className="font-medium">{b}</span>
              {b === "Yes, go ahead" && <Target kind="q" text={`Intro + Q1 · ${qs[0]?.label || "—"}`} />}
              {b === "Not now" && <Target kind="nurture" text="Status: Nurture" />}
              {b === "Stop" && <Target kind="stop" text="Unsubscribed" />}
            </div>
          ))}
        </div>
      </Node>
      <Down />
      {flow.intro_message && (
        <>
          <Node n={<Building2 className="h-3 w-3" />} title="Intro + property card (sent with Q1)" subtitle={fmt(flow.intro_message, prop).trim()} />
          <Down />
        </>
      )}
      {qs.map((q, i) => (
        <div key={q.key}>
          <Node n={`Q${i + 1}`} title={q.label} subtitle={fmt(q.prompt, prop)}>
            {!live.has(i) && <div className="mb-1 rounded bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">No option leads here — this question is never asked.</div>}
            <div className="space-y-1">
              {q.options.map((o) => {
                const t = targetLabel(qs, i, o);
                return (
                  <div key={o.id} className="rounded-md bg-slate-50 px-2 py-1 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{o.title}</span>
                      <Target kind={t.kind} text={t.text} />
                    </div>
                    {o.reply && (
                      <div className="mt-0.5 flex gap-1 text-[11px] text-slate-500">
                        <MessageSquareReply className="mt-0.5 h-3 w-3 shrink-0" />
                        <span className="line-clamp-2 whitespace-pre-wrap">{fmt(o.reply, prop)}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Node>
          {i < qs.length - 1 && <Down />}
        </div>
      ))}
      <Down />
      <Node n={<CheckCircle2 className="h-3.5 w-3.5" />} tone="green" title="Closing message"
        subtitle={fmt(flow.closing_message, prop)}>
        <div className="text-[11px] text-slate-600">Then the CRM marks the lead <b>Qualified</b>, scores it <b className="text-red-600">HOT</b>/<b className="text-amber-700">WARM</b>/<b className="text-blue-700">COLD</b>, assigns an agent and creates a follow-up (HOT 15 min · WARM 1 day · COLD 3 days).</div>
      </Node>

      <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3 text-[11px] text-slate-600">
        <div className="mb-1 text-xs font-semibold text-navy">At any point in the chat</div>
        <div className="flex items-start gap-1.5"><Ban className="mt-0.5 h-3 w-3 text-red-600" /> Customer types <b>STOP</b> → "{STOP_REPLY}" · nothing more is ever sent.</div>
        <div className="flex items-start gap-1.5"><UserRound className="mt-0.5 h-3 w-3 text-violet-600" /> Types "call me", "agent", "talk to someone" → "{HANDOFF_REPLY}" · agent notified.</div>
        <div className="flex items-start gap-1.5"><MessageSquareReply className="mt-0.5 h-3 w-3 text-amber-600" /> Types something that isn't an option → options sent again; 2nd time → hand to a person.</div>
        <div className="flex items-start gap-1.5"><PauseCircle className="mt-0.5 h-3 w-3 text-teal-700" /> Agent clicks <b>Take over</b> in Conversations → bot stops, agent's messages go to the customer. <b>Return to bot</b> continues from the next unanswered question.</div>
        <div className="mt-1 text-slate-500">"Not now" reply: "{NOT_NOW_REPLY}"</div>
      </div>
    </div>
  );
}
