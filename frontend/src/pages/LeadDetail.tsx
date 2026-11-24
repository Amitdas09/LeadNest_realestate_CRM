import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CalendarPlus, Check, Eye, MessageSquare, Send, ShieldCheck, StickyNote } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Avatar, Button, Card, ConsentChip, ErrorBox, Field, Loading, Modal, ModeChip, PriorityChip, StatusChip, useToast } from "../components/ui";
import { api } from "../lib/api";
import { isManager, useAuth } from "../lib/auth";
import { ACTION_LABEL, dateTime, humanize, STATUS_LABEL, timeAgo } from "../lib/format";

const STAGES = ["new", "contacted", "qualified", "site_visit", "negotiation", "won"];

export default function LeadDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const [phone, setPhone] = useState<string | null>(null);
  const [statusOpen, setStatusOpen] = useState(false);
  const [fuOpen, setFuOpen] = useState(false);
  const [note, setNote] = useState("");
  const q = useQuery({ queryKey: ["lead", id], queryFn: () => api(`/api/v1/leads/${id}`), refetchInterval: 5000 });
  const opts = useQuery({ queryKey: ["lead-options"], queryFn: () => api("/api/v1/leads/meta/options") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["lead", id] });
  const onErr = (e: any) => toast(e.message, "error");

  const patch = useMutation({ mutationFn: (body: any) => api(`/api/v1/leads/${id}`, { method: "PATCH", body }), onSuccess: () => { refresh(); toast("Saved"); }, onError: onErr });
  const addNote = useMutation({ mutationFn: () => api(`/api/v1/leads/${id}/notes`, { body: { body: note } }), onSuccess: () => { setNote(""); refresh(); }, onError: onErr });
  const start = useMutation({ mutationFn: () => api(`/api/v1/leads/${id}/start-whatsapp`, { body: {} }), onSuccess: () => { refresh(); toast("WhatsApp opening message on its way"); }, onError: onErr });
  const editReq = useMutation({ mutationFn: (body: any) => api(`/api/v1/leads/${id}/requirements`, { method: "PUT", body }), onSuccess: () => { refresh(); toast("Requirement updated"); }, onError: onErr });
  const done = useMutation({ mutationFn: (fid: number) => api(`/api/v1/followups/${fid}/done`, { body: {} }), onSuccess: refresh, onError: onErr });
  const reveal = async () => { try { setPhone((await api(`/api/v1/leads/${id}/phone`)).phone); } catch (e) { onErr(e); } };

  if (q.isLoading) return <div className="p-6"><Loading rows={6} /></div>;
  if (q.error) return <div className="p-6"><ErrorBox error={q.error} /></div>;
  const l = q.data;
  const answered = new Map(l.requirements.map((r: any) => [r.field_key, r]));
  const conv = l.conversation;
  const notStarted = !conv || conv.state === "new";
  const stageIdx = STAGES.indexOf(l.status);

  return (
    <div className="mx-auto max-w-[1440px] p-4 sm:p-6">

      <div className="card mb-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3 sm:gap-4">
            <Avatar name={l.full_name} size="lg" />
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold tracking-tight text-ink">{l.full_name}</h1>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-3">
                <span className="tabular">{phone || l.phone_masked}</span>
                {!phone && <button onClick={reveal} className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline" title="Revealing is recorded in the audit log"><Eye className="h-3.5 w-3.5" /> Reveal</button>}
                {l.email && <span className="break-all">{l.email}</span>}
                {l.property && <span>· {l.property.name}</span>}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5"><StatusChip status={l.status} /><PriorityChip priority={l.priority} /><ConsentChip status={l.consent_status} /><ModeChip mode={l.mode} /></div>
            </div>
          </div>
          <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto sm:flex-wrap">
            {notStarted && <Button variant="secondary" onClick={() => start.mutate()} loading={start.isPending}><Send className="h-4 w-4" /> Start WhatsApp</Button>}
            {conv && !notStarted && <Button variant="secondary" onClick={() => nav(`/conversations/${conv.id}`)}><MessageSquare className="h-4 w-4" /> Open chat</Button>}
            <Button variant="secondary" onClick={() => setFuOpen(true)}><CalendarPlus className="h-4 w-4" /> Follow-up</Button>
            <Button className="col-span-2 sm:col-span-1" onClick={() => setStatusOpen(true)} disabled={l.allowed_statuses.length === 0}>Change status</Button>
          </div>
        </div>
        {/* Stage tracker */}
        <ol className="mt-5 grid grid-cols-6 gap-1.5" aria-label="Sales stage">
          {STAGES.map((s, i) => {
            const reached = stageIdx >= 0 && i <= stageIdx;
            return (
              <li key={s}>
                <div className={clsx("h-1.5 rounded-full", reached ? (l.status === "won" ? "bg-green-600" : "bg-brand-600") : "bg-slate-100")} />
                <div className={clsx("mt-1.5 hidden items-center gap-1 text-2xs font-medium sm:flex", reached ? "text-ink" : "text-ink-4")}>
                  {reached && i < stageIdx && <Check className="h-3 w-3 text-brand-700" />}{STATUS_LABEL[s]}
                </div>
              </li>
            );
          })}
        </ol>
        <div className="mt-2 text-xs text-ink-3 sm:hidden">Stage: <b className="text-ink">{STATUS_LABEL[l.status] || l.status}</b>{stageIdx >= 0 && ` (${stageIdx + 1} of ${STAGES.length})`}</div>
        {["lost", "nurture"].includes(l.status) && <div className="mt-2 text-xs text-ink-3">Currently <b>{STATUS_LABEL[l.status]}</b>{l.status_reason && ` — ${l.status_reason}`}</div>}
      </div>

      {l.review_reasons.length > 0 && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <div><b>Automatic WhatsApp is on hold:</b> {l.review_reasons.join(" · ")}
            {l.review_reasons.some((r: string) => r.includes("map the form")) && <> — <Link to="/forms" className="font-semibold underline">open Forms & Flows</Link></>}</div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-4">
          <Card title="Source">
            <dl className="space-y-2 text-sm">
              {[["Meta lead ID", l.external_lead_id], ["Form", l.external_form_id], ["Campaign", l.campaign_name], ["Ad", l.ad_name], ["Platform", l.platform],
                ["Import", l.import_batch_id ? `Batch #${l.import_batch_id} · row ${l.source_row}` : l.source], ["Submitted", dateTime(l.source_created_at)],
                ["First reply sent", l.first_response_at ? dateTime(l.first_response_at) : "—"]].map(([k, v]) => (
                <div key={k as string} className="flex justify-between gap-3"><dt className="shrink-0 text-ink-3">{k}</dt><dd className="truncate text-right font-medium">{v || "—"}</dd></div>
              ))}
            </dl>
            {l.form_answers?.length > 0 && (
              <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs">
                <div className="mb-2 font-semibold text-ink-2">From the lead form</div>
                <dl className="space-y-1.5">
                  {l.form_answers.map((a: { label: string; value: string }) => (
                    <div key={a.label} className="flex justify-between gap-3">
                      <dt className="shrink-0 text-ink-3">{a.label}</dt>
                      <dd className="text-right font-medium text-ink-2">{a.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
            {isManager(user) && (
              <div className="mt-4"><Field label="Owner">
                <select className="input" value={l.owner?.id || ""} onChange={(e) => patch.mutate(e.target.value ? { owner_id: e.target.value } : { unassign: true })}>
                  <option value="">Unassigned</option>
                  {(opts.data?.users || []).map((u: any) => <option key={u.id} value={u.id}>{u.name} ({u.role})</option>)}
                </select></Field></div>
            )}
          </Card>
          <Card title="Consent" subtitle="Audited record">
            <ol className="space-y-3">
              {l.consent_records.map((c: any, i: number) => (
                <li key={i} className="text-sm">
                  <div className="flex items-center justify-between"><ConsentChip status={c.status} /><span className="text-xs text-ink-4">{dateTime(c.created_at)}</span></div>
                  <p className="mt-1 text-xs text-ink-3">{c.evidence}</p>
                </li>
              ))}
            </ol>
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          <Card title="Requirements" subtitle="Captured on WhatsApp — agents can correct any value" bodyClass="p-0">
            {l.questions.length === 0 ? <div className="p-4 text-sm text-ink-3">No question flow for this lead. Map its form in Forms & flows.</div> : (
              <table className="w-full">
                <thead><tr className="border-b border-line"><th className="th">Question</th><th className="th">Answer</th><th className="th hidden sm:table-cell">Customer said</th><th className="th hidden sm:table-cell">Source</th></tr></thead>
                <tbody>{l.questions.map((qq: any) => {
                  const r: any = answered.get(qq.key);
                  return (
                    <tr key={qq.key} className="border-b border-line/60 last:border-0">
                      <td className="td font-medium">{qq.label}</td>
                      <td className="td">
                        <select aria-label={qq.label} className="input sm:h-8 sm:text-xs" value={qq.options.find((o: any) => o.title === r?.display)?.id || ""}
                          onChange={(e) => e.target.value && editReq.mutate({ field_key: qq.key, option_id: e.target.value })}>
                          <option value="">Not captured</option>
                          {qq.options.map((o: any) => <option key={o.id} value={o.id}>{o.title}</option>)}
                        </select>
                      </td>
                      <td className="td hidden text-xs text-ink-3 sm:table-cell">{r ? `“${r.original_text}”` : "—"}</td>
                      <td className="td hidden text-xs sm:table-cell">{r ? (r.source === "agent" ? "Agent" : "WhatsApp") : "—"}</td>
                    </tr>
                  );
                })}</tbody>
              </table>
            )}
          </Card>
          <Card title="Internal notes" subtitle="Never sent to the customer" icon={<StickyNote className="h-4 w-4" />}>
            <form onSubmit={(e: FormEvent) => { e.preventDefault(); note.trim() && addNote.mutate(); }} className="mb-4 flex gap-2">
              <input aria-label="New note" className="input" placeholder="Add a note for your team…" value={note} onChange={(e) => setNote(e.target.value)} />
              <Button type="submit" loading={addNote.isPending} disabled={!note.trim()}>Add</Button>
            </form>
            {l.notes.length === 0 ? <div className="text-sm text-ink-4">No notes yet.</div> : (
              <ul className="space-y-3">{l.notes.map((n: any) => (
                <li key={n.id} className="flex gap-3">
                  <Avatar name={n.author?.name} size="sm" />
                  <div className="min-w-0 flex-1 rounded-xl bg-amber-50 px-3 py-2 text-sm ring-1 ring-amber-100">
                    <div className="mb-0.5 text-xs"><span className="font-semibold text-ink">{n.author?.name}</span> <span className="text-ink-3">· {dateTime(n.created_at)}</span></div>
                    <div className="whitespace-pre-wrap text-ink-2">{n.body}</div>
                  </div>
                </li>))}</ul>
            )}
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          <Card title="Follow-ups" action={<Button size="sm" variant="ghost" onClick={() => setFuOpen(true)}><CalendarPlus className="h-3.5 w-3.5" /> Add</Button>}>
            {l.follow_ups.length === 0 ? <div className="text-sm text-ink-4">None scheduled.</div> : (
              <ul className="space-y-2">{l.follow_ups.map((f: any) => {
                const overdue = f.status === "open" && new Date(f.due_at) < new Date();
                return (
                  <li key={f.id} className="flex items-start gap-2.5 rounded-lg border border-line p-2.5">
                    <button aria-label={f.status === "done" ? "Completed" : "Mark done"} disabled={f.status === "done"} onClick={() => done.mutate(f.id)}
                      className={clsx("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors sm:h-4 sm:w-4", f.status === "done" ? "border-brand-700 bg-brand-700 text-white" : "border-line-strong hover:border-brand-600")}>
                      {f.status === "done" && <Check className="h-3 w-3" />}
                    </button>
                    <div className="min-w-0 flex-1 text-sm">
                      <div className={clsx(f.status === "done" ? "text-ink-4 line-through" : "font-medium text-ink")}>{f.note || "Follow up"}</div>
                      <div className={clsx("text-xs", overdue ? "font-semibold text-red-600" : "text-ink-3")}>{overdue ? "Overdue · " : ""}{dateTime(f.due_at)} · {f.assigned_to?.name || "Unassigned"}</div>
                    </div>
                  </li>);
              })}</ul>
            )}
          </Card>
          <Card title="Activity" bodyClass="scroll-thin max-h-[480px] overflow-y-auto px-4 py-2">
            <ol>
              {l.timeline.map((e: any, i: number) => (
                <li key={e.id} className="relative flex gap-3 py-2">
                  {i < l.timeline.length - 1 && <span className="absolute left-[5px] top-5 h-full w-px bg-line" aria-hidden />}
                  <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-white bg-brand-600 ring-1 ring-brand-200" />
                  <div className="min-w-0 flex-1 text-sm">
                    <div className="font-medium text-ink">{ACTION_LABEL[e.action] || e.action}
                      {e.details?.to && e.action === "lead.status_change" && <span className="text-ink-3"> → {STATUS_LABEL[e.details.to] || e.details.to}</span>}
                      {e.details?.priority && <span className="text-ink-3"> · {String(e.details.priority).toUpperCase()}</span>}
                      {e.details?.reason && e.action === "conversation.handoff" && <span className="text-ink-3"> · {humanize(e.details.reason)}</span>}
                    </div>
                    <div className="text-xs text-ink-3">{e.actor?.name || (e.actor_type === "system" ? "System" : "—")} · {timeAgo(e.at)}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>

      <StatusModal open={statusOpen} onClose={() => setStatusOpen(false)} lead={l} onSave={(b: any) => patch.mutateAsync(b).then(() => setStatusOpen(false))} />
      <FollowUpModal open={fuOpen} onClose={() => setFuOpen(false)} leadId={l.id} onDone={() => { setFuOpen(false); refresh(); toast("Follow-up scheduled"); }} />
    </div>
  );
}

function StatusModal({ open, onClose, lead, onSave }: any) {
  const [status, setStatus] = useState("");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<any>(null);
  const needReason = status === "won" || status === "lost";
  return (
    <Modal open={open} onClose={onClose} title="Change status" description={`Currently ${STATUS_LABEL[lead.status]}. Only valid next stages are shown.`}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="New status">
          {lead.allowed_statuses.map((s: string) => (
            <button key={s} role="radio" aria-checked={status === s} onClick={() => setStatus(s)}
              className={clsx("flex h-10 items-center justify-center rounded-lg border text-sm font-medium transition-colors", status === s ? "border-brand-700 bg-brand-50 text-brand-800" : "border-line hover:bg-slate-50")}>
              {STATUS_LABEL[s]}
            </button>
          ))}
        </div>
        <Field label={needReason ? "Reason *" : "Reason (optional)"}><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder={status === "lost" ? "e.g. Bought elsewhere" : ""} /></Field>
        <ErrorBox error={err} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button disabled={!status || (needReason && !reason.trim())} onClick={() => onSave({ status, status_reason: reason || null }).catch(setErr)}>Save</Button>
        </div>
      </div>
    </Modal>
  );
}

function FollowUpModal({ open, onClose, leadId, onDone }: any) {
  const tomorrow = new Date(Date.now() + 86400000);
  tomorrow.setHours(11, 0, 0, 0);
  const local = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const [due, setDue] = useState(local);
  const [note, setNote] = useState("");
  const m = useMutation({ mutationFn: () => api(`/api/v1/leads/${leadId}/followups`, { body: { due_at: new Date(due).toISOString(), note } }), onSuccess: onDone });
  return (
    <Modal open={open} onClose={onClose} title="Schedule follow-up">
      <div className="space-y-4">
        <Field label="Due"><input type="datetime-local" className="input" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
        <Field label="What to do"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Call to confirm Saturday site visit" /></Field>
        <ErrorBox error={m.error} />
        <div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} onClick={() => m.mutate()}>Schedule</Button></div>
      </div>
    </Modal>
  );
}
