import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import FlowMap from "../components/FlowMap";
import FlowSimulator from "../components/FlowSimulator";
import { Button, Card, Chip, Empty, ErrorBox, Field, Loading, Modal, PageHeader, Tabs, Toggle, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { END, HANDOFF } from "../lib/flow";

export default function Forms() {
  const [tab, setTab] = useState<"flows" | "forms">("flows");
  return (
    <div className="mx-auto max-w-[1600px] p-6">
      <PageHeader title="Forms & question flows"
        subtitle="Each Meta form → a property → a WhatsApp question flow. Every button decides what happens next."
        actions={<Tabs value={tab} onChange={setTab} items={[{ value: "flows", label: "Question flows" }, { value: "forms", label: "Meta forms" }]} />} />
      {tab === "forms" ? <FormsTab /> : <FlowsTab />}
    </div>
  );
}

function FormsTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const forms = useQuery({ queryKey: ["forms"], queryFn: () => api("/api/v1/forms") });
  const props = useQuery({ queryKey: ["properties"], queryFn: () => api("/api/v1/properties") });
  const flows = useQuery({ queryKey: ["flows"], queryFn: () => api("/api/v1/flows") });
  const [adding, setAdding] = useState(false);
  const update = useMutation({
    mutationFn: ({ id, body }: any) => api(`/api/v1/forms/${id}`, { method: "PATCH", body }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["forms"] }); toast("Form updated"); },
    onError: (e: any) => toast(e.message, "error"),
  });
  if (forms.isLoading) return <Loading />;
  return (
    <>
      <ErrorBox error={forms.error} />
      <div className="mb-3 flex justify-end">{admin && <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add form</Button>}</div>
      <div className="card overflow-x-auto">
        {forms.data.items.length === 0 ? <Empty title="No forms yet" hint="Forms appear automatically when the sheet import sees a new form ID, or add one here." /> : (
          <table className="w-full min-w-[960px]">
            <thead><tr className="border-b border-slate-100">{["Meta form", "Leads", "Property", "Question flow", "WhatsApp consent", "Auto-message", "Status"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody>{forms.data.items.map((f: any) => (
              <tr key={f.id} className="border-b border-slate-50">
                <td className="td"><div className="font-semibold text-navy">{f.form_name}</div><div className="font-mono text-[11px] text-slate-500">{f.external_form_id}</div></td>
                <td className="td">{f.lead_count}</td>
                <td className="td"><select className="input py-1" disabled={!admin} value={f.property?.id || ""} onChange={(e) => update.mutate({ id: f.id, body: { property_id: e.target.value || null } })}>
                  <option value="">— choose —</option>{(props.data?.items || []).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></td>
                <td className="td"><select className="input py-1" disabled={!admin} value={f.flow?.id || ""} onChange={(e) => update.mutate({ id: f.id, body: { flow_id: e.target.value || null } })}>
                  <option value="">— choose —</option>{(flows.data?.items || []).map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></td>
                <td className="td"><select className="input py-1" disabled={!admin} value={f.consent_mode} onChange={(e) => update.mutate({ id: f.id, body: { consent_mode: e.target.value } })}>
                  <option value="column">Read sheet column</option><option value="form">Form has WhatsApp disclosure</option><option value="none">Never auto-message</option></select></td>
                <td className="td"><Toggle checked={f.auto_message} disabled={!admin} onChange={(v) => update.mutate({ id: f.id, body: { auto_message: v } })} /></td>
                <td className="td">{f.mapped ? <Chip className="bg-emerald-50 text-emerald-700 ring-emerald-200">Live</Chip> : <Chip className="bg-amber-50 text-amber-800 ring-amber-200">Unmapped</Chip>}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>
      <AddForm open={adding} onClose={() => setAdding(false)} props={props.data?.items || []} flows={flows.data?.items || []} />
    </>
  );
}

function AddForm({ open, onClose, props, flows }: any) {
  const qc = useQueryClient();
  const [f, setF] = useState<any>({ external_form_id: "", form_name: "", property_id: "", flow_id: "", consent_mode: "column" });
  const m = useMutation({
    mutationFn: () => api("/api/v1/forms", { body: { ...f, property_id: f.property_id || null, flow_id: f.flow_id || null } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["forms"] }); onClose(); },
  });
  const up = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal open={open} onClose={onClose} title="Add Meta form">
      <div className="space-y-3">
        <Field label="Form ID (from the sheet's form_id column, without f:)"><input className="input font-mono" value={f.external_form_id} onChange={up("external_form_id")} /></Field>
        <Field label="Form name"><input className="input" value={f.form_name} onChange={up("form_name")} /></Field>
        <Field label="Property"><select className="input" value={f.property_id} onChange={up("property_id")}><option value="">— choose —</option>{props.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
        <Field label="Question flow"><select className="input" value={f.flow_id} onChange={up("flow_id")}><option value="">— choose —</option>{flows.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        <ErrorBox error={m.error} />
        <div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} onClick={() => m.mutate()}>Add form</Button></div>
      </div>
    </Modal>
  );
}

const optionValues = (draft: any, key: string): string[] =>
  (draft?.questions || []).find((q: any) => q.key === key)?.options.map((o: any) => String(o.value)) || [];

function FlowsTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const flows = useQuery({ queryKey: ["flows"], queryFn: () => api("/api/v1/flows") });
  const props = useQuery({ queryKey: ["properties"], queryFn: () => api("/api/v1/properties") });
  const forms = useQuery({ queryKey: ["forms"], queryFn: () => api("/api/v1/forms") });
  const [sel, setSel] = useState<string | null>(null);
  const [draft, setDraft] = useState<any>(null);
  const [side, setSide] = useState<"map" | "test" | "rules">("map");
  const [previewProp, setPreviewProp] = useState<string>("");
  const items = flows.data?.items || [];
  useEffect(() => { if (!sel && items.length) setSel(items[0].id); }, [items, sel]);
  useEffect(() => { const f = items.find((x: any) => x.id === sel); if (f) setDraft(JSON.parse(JSON.stringify(f))); }, [sel, flows.data]);

  // Preview with a property that actually uses this flow (via a mapped form), if there is one.
  const propList = props.data?.items || [];
  useEffect(() => {
    const viaForm = (forms.data?.items || []).find((f: any) => f.flow?.id === sel && f.property)?.property?.id;
    setPreviewProp(viaForm || propList[0]?.id || "");
  }, [sel, forms.data, props.data]);
  const prop = useMemo(() => propList.find((p: any) => p.id === previewProp), [propList, previewProp]);

  const save = useMutation({
    mutationFn: () => api(`/api/v1/flows/${sel}`, { method: "PUT", body: { name: draft.name, intro_message: draft.intro_message, closing_message: draft.closing_message, questions: draft.questions, rules: draft.rules } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["flows"] }); toast("Flow published"); },
  });
  if (flows.isLoading || !draft) return <Loading />;
  const qs = draft.questions;
  const TIMELINE_KEYS = optionValues(draft, "timeline");
  const NEXT_KEYS = optionValues(draft, "next_step");
  const setQ = (i: number, patch: any) => setDraft({ ...draft, questions: qs.map((q: any, j: number) => (j === i ? { ...q, ...patch } : q)) });
  const setOpt = (i: number, k: number, patch: any) => setQ(i, { options: qs[i].options.map((o: any, j: number) => (j === k ? { ...o, ...patch } : o)) });
  const move = (i: number, d: number) => { const n = [...qs]; [n[i], n[i + d]] = [n[i + d], n[i]]; setDraft({ ...draft, questions: n }); };
  const toggleRule = (tier: "hot" | "warm", field: string, key: string) => {
    const list: string[] = draft.rules[tier]?.[field] || [];
    const next = list.includes(key) ? list.filter((x) => x !== key) : [...list, key];
    setDraft({ ...draft, rules: { ...draft.rules, [tier]: { ...draft.rules[tier], [field]: next } } });
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[200px_minmax(0,1fr)_380px]">
      <div className="card h-fit overflow-hidden">
        {items.map((f: any) => (
          <button key={f.id} onClick={() => setSel(f.id)} className={clsx("block w-full border-b border-slate-50 px-4 py-3 text-left hover:bg-slate-50", sel === f.id && "border-l-[3px] border-l-teal bg-teal-50/60")}>
            <div className="font-semibold text-navy">{f.name}</div>
            <div className="text-[11px] text-slate-500">v{f.version} · {f.questions.length} questions · {f.active_conversations} live chats</div>
          </button>
        ))}
      </div>

      <div className="space-y-3">
        <Card title="Messages">
          <div className="space-y-3">
            <Field label="Flow name"><input className="input" disabled={!admin} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
            <Field label="Intro + property card (sent with the first question, after 'Yes, go ahead')" hint="{name} first name · {property} property name · {property_details} location/price/possession · {brochure} brochure link">
              <textarea className="input min-h-[70px]" disabled={!admin} value={draft.intro_message} onChange={(e) => setDraft({ ...draft, intro_message: e.target.value })} /></Field>
            <Field label="Closing message (after the last answer)"><textarea className="input min-h-[70px]" disabled={!admin} value={draft.closing_message} onChange={(e) => setDraft({ ...draft, closing_message: e.target.value })} /></Field>
          </div>
        </Card>

        {qs.map((q: any, i: number) => (
          <div key={q.key + i} className="card p-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-teal px-1.5 text-xs font-bold text-white">Q{i + 1}</span>
              <input className="input flex-1 font-semibold" disabled={!admin} value={q.label} onChange={(e) => setQ(i, { label: e.target.value })} />
              <span className="font-mono text-[11px] text-slate-400">{q.key}</span>
              {admin && <>
                <button disabled={i === 0} onClick={() => move(i, -1)} className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30" title="Move up"><ArrowUp className="h-3.5 w-3.5" /></button>
                <button disabled={i === qs.length - 1} onClick={() => move(i, 1)} className="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30" title="Move down"><ArrowDown className="h-3.5 w-3.5" /></button>
                {!["timeline", "next_step"].includes(q.key) && <button onClick={() => setDraft({ ...draft, questions: qs.filter((_: any, j: number) => j !== i) })} className="rounded p-1 text-red-500 hover:bg-red-50" title="Delete question"><Trash2 className="h-3.5 w-3.5" /></button>}
              </>}
            </div>
            <input className="input mb-2" disabled={!admin} value={q.prompt} onChange={(e) => setQ(i, { prompt: e.target.value })} placeholder="Question the customer sees" />
            <div className="overflow-hidden rounded-lg border border-slate-200">
              <div className="grid grid-cols-[minmax(0,1fr)_190px_28px] gap-2 bg-slate-50 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                <span>Button (max 20 chars)</span><span>Then go to</span><span />
              </div>
              {q.options.map((o: any, k: number) => (
                <div key={o.id} className="border-t border-slate-100 px-2 py-1.5">
                  <div className="grid grid-cols-[minmax(0,1fr)_190px_28px] items-center gap-2">
                    <input className="input py-1 text-xs" maxLength={20} disabled={!admin} value={o.title} onChange={(e) => setOpt(i, k, { title: e.target.value })} />
                    <select className="input py-1 text-xs" disabled={!admin} value={o.next || ""} onChange={(e) => setOpt(i, k, { next: e.target.value || null })}>
                      <option value="">{i + 1 < qs.length ? `Next: Q${i + 2} ${qs[i + 1].label}` : "Closing message"}</option>
                      {qs.slice(i + 2).map((t: any, j: number) => <option key={t.key} value={t.key}>Q{i + 3 + j} {t.label}</option>)}
                      <option value={END}>Closing message (finish)</option>
                      <option value={HANDOFF}>Hand to a person</option>
                    </select>
                    {admin && q.options.length > 2
                      ? <button onClick={() => setQ(i, { options: q.options.filter((_: any, j: number) => j !== k) })} className="text-slate-400 hover:text-red-500" title="Remove option"><Trash2 className="h-3.5 w-3.5" /></button>
                      : <span />}
                  </div>
                  <input className="input mt-1 py-1 text-[11px]" disabled={!admin} value={o.reply || ""} onChange={(e) => setOpt(i, k, { reply: e.target.value || null })}
                    placeholder="Optional reply sent right after this choice (e.g. '📅 Great! We'll plan your visit.')" />
                </div>
              ))}
            </div>
            {admin && q.options.length < 3 && (
              <button onClick={() => { const id = `${q.key}_${Date.now().toString(36)}`; setQ(i, { options: [...q.options, { id, title: "New option", value: id }] }); }}
                className="mt-1.5 rounded-md border border-dashed border-slate-300 px-2 py-1 text-xs text-slate-500 hover:border-teal hover:text-teal-700">+ option (max 3 buttons)</button>
            )}
          </div>
        ))}
        {admin && (
          <Button variant="secondary" onClick={() => {
            const key = `q_${Date.now().toString(36)}`;
            const at = qs.findIndex((q: any) => q.key === "timeline");
            const n = [...qs];
            n.splice(at < 0 ? n.length : at, 0, { key, label: "New question", prompt: "Your question?", options: [{ id: `${key}_a`, title: "Option A", value: "a" }, { id: `${key}_b`, title: "Option B", value: "b" }] });
            setDraft({ ...draft, questions: n });
          }}><Plus className="h-4 w-4" /> Add question</Button>
        )}
      </div>

      <div className="space-y-3">
        <div className="card p-2">
          <div className="mb-2 flex rounded-lg bg-slate-100 p-0.5">
            {([["map", "Flow map"], ["test", "Test chat"], ["rules", "Scoring"]] as const).map(([k, l]) => (
              <button key={k} onClick={() => setSide(k)} className={clsx("flex-1 rounded-md px-2 py-1 text-xs font-semibold", side === k ? "bg-white text-navy shadow-sm" : "text-slate-500")}>{l}</button>
            ))}
          </div>
          {side !== "rules" && (
            <div className="mb-2 flex items-center gap-2 px-1 text-[11px] text-slate-500">
              Preview with property
              <select className="input w-auto flex-1 py-0.5 text-xs" value={previewProp} onChange={(e) => setPreviewProp(e.target.value)}>
                {propList.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}
          <div className="max-h-[calc(100vh-260px)] overflow-y-auto px-1 pb-1">
            {side === "map" && <FlowMap flow={draft} prop={prop} />}
            {side === "test" && <FlowSimulator flow={draft} prop={prop} />}
            {side === "rules" && (
              <div className="space-y-3 p-1 text-xs">
                <div><div className="mb-1 font-bold text-red-600">HOT when timeline is…</div>
                  <div className="flex flex-wrap gap-1">{TIMELINE_KEYS.map((k) => <RuleChip key={k} on={(draft.rules.hot?.timeline_in || []).includes(k)} label={k} disabled={!admin} onClick={() => toggleRule("hot", "timeline_in", k)} />)}</div>
                  <div className="mb-1 mt-2 font-bold text-red-600">…and next step is</div>
                  <div className="flex flex-wrap gap-1">{NEXT_KEYS.map((k) => <RuleChip key={k} on={(draft.rules.hot?.next_step_in || []).includes(k)} label={k} disabled={!admin} onClick={() => toggleRule("hot", "next_step_in", k)} />)}</div></div>
                <div><div className="mb-1 font-bold text-amber-700">WARM when timeline is…</div>
                  <div className="flex flex-wrap gap-1">{TIMELINE_KEYS.map((k) => <RuleChip key={k} on={(draft.rules.warm?.timeline_in || []).includes(k)} label={k} disabled={!admin} onClick={() => toggleRule("warm", "timeline_in", k)} />)}</div></div>
                <div className="font-bold text-blue-700">COLD: everything else.</div>
                <label className="flex items-center gap-2"><Toggle checked={!!draft.rules.budget_below_min_downgrade} disabled={!admin} onChange={(v) => setDraft({ ...draft, rules: { ...draft.rules, budget_below_min_downgrade: v } })} />
                  Budget below the property's starting price → drop one level</label>
              </div>
            )}
          </div>
        </div>
        {admin && (
          <div className="card p-3">
            {draft.active_conversations > 0 && <div className="mb-2 text-[11px] text-amber-700">{draft.active_conversations} chat(s) are mid-flow and will use the new questions from their next step.</div>}
            <ErrorBox error={save.error} />
            {(save.error as any)?.fieldErrors && Object.values((save.error as any).fieldErrors).map((m: any, i) => <div key={i} className="mt-1 text-[11px] text-red-600">{m}</div>)}
            <Button className="mt-1 w-full" loading={save.isPending} onClick={() => save.mutate()}>Publish v{draft.version + 1}</Button>
          </div>
        )}
      </div>
    </div>
  );
}

function RuleChip({ on, label, onClick, disabled }: any) {
  return (
    <button disabled={disabled} onClick={onClick}
      className={clsx("rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset", on ? "bg-navy text-white ring-navy" : "bg-white text-slate-500 ring-slate-200")}>
      {label.replace(/_/g, " ")}
    </button>
  );
}
