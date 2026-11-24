import clsx from "clsx";
import { RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { computePriority, END, Flow, fmt, HANDOFF, HANDOFF_REPLY, nextIndex, NOT_NOW_REPLY, Prop, STOP_REPLY, TEMPLATE_BUTTONS } from "../lib/flow";

type Msg = { from: "bot" | "me"; text: string; buttons?: string[] };
type Stage = { kind: "template" } | { kind: "q"; i: number } | { kind: "done"; outcome: string };

/** Tap through a flow exactly as a customer would on WhatsApp. Nothing is sent. */
export default function FlowSimulator({ flow, prop }: { flow: Flow; prop?: Prop | null }) {
  const qs = flow.questions;
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [stage, setStage] = useState<Stage>({ kind: "template" });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [answerTitles, setAnswerTitles] = useState<Record<string, string>>({});
  const end = useRef<HTMLDivElement>(null);

  const reset = () => {
    setMsgs([{ from: "bot", text: `Hi Amit, thank you for your enquiry about ${prop?.name || "our project"}! 🏡\n\nI'm the virtual property assistant. May I ask you a few quick questions so our team can share the best options for you?\n\nReply STOP to unsubscribe`, buttons: TEMPLATE_BUTTONS }]);
    setStage({ kind: "template" });
    setAnswers({});
    setAnswerTitles({});
  };
  useEffect(reset, [flow, prop?.name]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [msgs.length]);

  const ask = (i: number, prefix = ""): Msg => ({ from: "bot", text: prefix + fmt(qs[i].prompt, prop), buttons: qs[i].options.map((o) => o.title) });

  const tap = (title: string) => {
    const out: Msg[] = [{ from: "me", text: title }];
    if (stage.kind === "template") {
      if (title === "Stop") { out.push({ from: "bot", text: STOP_REPLY }); setStage({ kind: "done", outcome: "Unsubscribed · never messaged again" }); }
      else if (title === "Not now") { out.push({ from: "bot", text: NOT_NOW_REPLY }); setStage({ kind: "done", outcome: "Lead status → Nurture" }); }
      else if (qs.length) { out.push(ask(0, flow.intro_message ? fmt(flow.intro_message, prop) : "")); setStage({ kind: "q", i: 0 }); }
    } else if (stage.kind === "q") {
      const q = qs[stage.i];
      const o = q.options.find((x) => x.title === title)!;
      const a = { ...answers, [q.key]: String(o.value) };
      setAnswers(a);
      setAnswerTitles({ ...answerTitles, [q.label]: o.title });
      if (o.reply) out.push({ from: "bot", text: fmt(o.reply, prop) });
      const n = nextIndex(qs, stage.i, o);
      const p = computePriority(flow, a, prop?.price_min);
      if (n === HANDOFF) {
        if (!o.reply) out.push({ from: "bot", text: HANDOFF_REPLY });
        setStage({ kind: "done", outcome: `Handed to a person · ${p.toUpperCase()} lead` });
      } else if (n === END || (n as number) >= qs.length) {
        out.push({ from: "bot", text: fmt(flow.closing_message, prop) });
        setStage({ kind: "done", outcome: `Qualified · ${p.toUpperCase()} lead · agent assigned + follow-up` });
      } else {
        out.push(ask(n as number));
        setStage({ kind: "q", i: n as number });
      }
    }
    setMsgs((m) => [...m.map((x) => ({ ...x, buttons: undefined })), ...out]);
  };

  const lastButtons = stage.kind !== "done" ? msgs[msgs.length - 1]?.buttons : undefined;
  return (
    <div>
      <div className="mx-auto w-full max-w-[300px] overflow-hidden rounded-[28px] border-[6px] border-slate-900 bg-slate-900 shadow-xl">
        <div className="flex items-center gap-2 bg-[#075E54] px-3 py-2 text-white">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white/20 text-xs font-bold">{(prop?.name || "P")[0]}</div>
          <div className="min-w-0"><div className="truncate text-xs font-semibold">{prop?.name || "Property"} ✓</div><div className="text-[10px] opacity-80">Business account</div></div>
        </div>
        <div className="chat-bg h-[430px] space-y-1.5 overflow-y-auto px-2 py-2">
          {msgs.map((m, i) => (
            <div key={i} className={clsx("flex", m.from === "me" ? "justify-end" : "justify-start")}>
              <div className={clsx("max-w-[85%] rounded-lg px-2 py-1 text-[11.5px] shadow-sm", m.from === "me" ? "bg-wa-bubble" : "bg-white")}>
                <div className="whitespace-pre-wrap">{m.text}</div>
                {m.buttons && i === msgs.length - 1 && stage.kind !== "done" && (
                  <div className="-mx-2 mt-1.5 border-t border-slate-100">
                    {m.buttons.map((b) => (
                      <button key={b} onClick={() => tap(b)} className="block w-full border-b border-slate-100 py-1.5 text-center text-[11.5px] font-semibold text-[#00A884] last:border-0 hover:bg-slate-50">{b}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={end} />
        </div>
      </div>
      {!lastButtons && stage.kind === "done" && (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-xs">
          <div className="font-semibold text-emerald-800">Result in the CRM: {stage.outcome}</div>
          {Object.keys(answerTitles).length > 0 && (
            <div className="mt-1 space-y-0.5 text-emerald-900">{Object.entries(answerTitles).map(([k, v]) => <div key={k}>• {k}: <b>{v}</b></div>)}</div>
          )}
        </div>
      )}
      <button onClick={reset} className="mx-auto mt-2 flex items-center gap-1 text-xs font-semibold text-teal-700 hover:underline"><RotateCcw className="h-3 w-3" /> Start again</button>
      <div className="mt-1 text-center text-[10px] text-slate-400">Preview only — nothing is sent. Uses the unsaved draft.</div>
    </div>
  );
}
