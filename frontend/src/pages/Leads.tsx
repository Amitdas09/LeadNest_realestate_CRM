import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, Download, Search, SlidersHorizontal, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Avatar, Button, ConsentChip, Empty, ErrorBox, Field, Loading, Modal, ModeChip, PageHeader, PriorityChip, StatusChip, Tabs, Toggle, useToast } from "../components/ui";
import { api } from "../lib/api";
import { isManager, useAuth } from "../lib/auth";
import { STATUS_LABEL, timeAgo } from "../lib/format";

const CHIPS = [
  { value: "", label: "All", key: "all" },
  { value: "unread", label: "Unread", key: "unread" },
  { value: "needs_review", label: "Needs review", key: "needs_review" },
  { value: "hot", label: "Hot", key: "hot" },
  { value: "unassigned", label: "Unassigned", key: "unassigned" },
  { value: "followup_due", label: "Follow-up due", key: "followup_due" },
];
const PAGE = 25;

export default function Leads() {
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [adding, setAdding] = useState(sp.get("add") === "1");
  const [showFilters, setShowFilters] = useState(false); // phones: filters behind a button
  // "+ Add lead" in the top bar opens this page with ?add=1.
  useEffect(() => {
    if (sp.get("add") === "1") { setAdding(true); const n = new URLSearchParams(sp); n.delete("add"); setSp(n, { replace: true }); }
  }, [sp, setSp]);
  const params = Object.fromEntries([...sp.entries()].filter(([k]) => k !== "add"));
  const page = Number(params.page || 0);
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); v ? n.set(k, v) : n.delete(k); n.delete("page"); setSp(n); };
  const setPage = (p: number) => { const n = new URLSearchParams(sp); n.set("page", String(p)); setSp(n); };

  const opts = useQuery({ queryKey: ["lead-options"], queryFn: () => api("/api/v1/leads/meta/options") });
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["leads", params],
    queryFn: () => api("/api/v1/leads", { query: { ...params, page: undefined, limit: PAGE, offset: page * PAGE } }),
    refetchInterval: 5000,
    placeholderData: keepPreviousData,
  });

  const exportCsv = () => {
    const rows = [["Name", "Phone (masked)", "Property", "Form", "Status", "Priority", "Owner", "Consent", "Last activity"],
      ...(data?.items || []).map((l: any) => [l.full_name, l.phone_masked, l.property?.name || "", l.form?.external_form_id || "", l.status, l.priority || "", l.owner?.name || "", l.consent_status, l.last_activity_at])];
    const csv = rows.map((r) => r.map((c: any) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "leads.csv";
    a.click();
  };

  const select = (k: string, label: string, options: [string, string][]) => (
    <select aria-label={label} className="input sm:h-8 sm:w-auto sm:max-w-[180px] sm:text-xs" value={params[k] || ""} onChange={(e) => set(k, e.target.value)}>
      <option value="">{label}: All</option>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
  const filterKeys = ["property_id", "status", "priority", "owner", "mode"];
  const filtered = ["q", ...filterKeys].some((k) => params[k]);
  const activeFilters = filterKeys.filter((k) => params[k]).length;

  return (
    <div className="mx-auto max-w-[1440px] p-4 sm:p-6">
      <PageHeader title="Leads" subtitle={data ? `${data.total} lead${data.total === 1 ? "" : "s"}${filtered ? " match your filters" : ""}` : "Loading…"}
        actions={<Button variant="secondary" onClick={exportCsv}><Download className="h-4 w-4" /> Export<span className="hidden sm:inline"> CSV</span></Button>} />

      <div className="mb-4">
        <Tabs value={params.chip || ""} onChange={(v) => set("chip", v)} items={CHIPS.map((c) => ({ value: c.value, label: c.label, count: data?.chips?.[c.key] }))} />
      </div>

      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-0 flex-1 sm:w-64 sm:flex-none">
            <Search className="pointer-events-none absolute left-2.5 top-3 h-4 w-4 text-ink-4 sm:top-2" aria-hidden />
            <input aria-label="Search leads" className="input pl-8 sm:h-8 sm:text-xs" placeholder="Search name, phone, lead ID" defaultValue={params.q || ""}
              enterKeyHint="search" onKeyDown={(e) => e.key === "Enter" && set("q", (e.target as HTMLInputElement).value)} />
          </div>
          <Button variant="secondary" className="sm:hidden" onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}>
            <SlidersHorizontal className="h-4 w-4" /> Filters{activeFilters > 0 && <span className="rounded-full bg-brand-700 px-1.5 text-2xs text-white">{activeFilters}</span>}
          </Button>
          <div className={clsx("w-full grid-cols-2 gap-2 sm:flex sm:w-auto sm:flex-wrap sm:items-center", showFilters ? "grid" : "hidden")}>
            {select("property_id", "Property", (opts.data?.properties || []).map((p: any) => [p.id, p.name]))}
            {select("status", "Status", Object.entries(STATUS_LABEL))}
            {select("priority", "Priority", [["hot", "Hot"], ["warm", "Warm"], ["cold", "Cold"]])}
            {isManager(user) && select("owner", "Owner", [["unassigned", "Unassigned"], ...(opts.data?.users || []).map((u: any) => [u.id, u.name])])}
            {select("mode", "Chat", [["bot", "Bot"], ["human", "Human"], ["handoff", "Needs person"], ["blocked", "No consent"]])}
          </div>
          {sp.toString() && <Button variant="ghost" size="sm" onClick={() => setSp(new URLSearchParams())}><X className="h-3.5 w-3.5" /> Clear</Button>}
          {isFetching && !isLoading && <span className="ml-auto hidden text-2xs text-ink-4 sm:inline">Updating…</span>}
        </div>
        <ErrorBox error={error} />
        <div className="scroll-thin overflow-x-auto">
          {isLoading ? <Loading rows={8} /> : data.items.length === 0 ? (
            <Empty title={filtered ? "No leads match these filters" : "No leads yet"} hint="New rows in your Google Sheet appear here within a minute."
              action={filtered ? <Button variant="secondary" size="sm" onClick={() => setSp(new URLSearchParams())}>Clear filters</Button> : undefined} />
          ) : (<>
            {/* Phone: one tappable card per lead */}
            <ul className="divide-y divide-line/60 md:hidden">
              {data.items.map((l: any) => (
                <li key={l.id}>
                  <button onClick={() => nav(`/leads/${l.id}`)} className="flex w-full items-start gap-3 px-3 py-3 text-left active:bg-slate-50">
                    <div className="relative">
                      <Avatar name={l.full_name} />
                      {l.unread_count > 0 && <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-brand-600 ring-2 ring-white" aria-label="Unread messages" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-semibold text-ink">{l.full_name}</span>
                        <span className="shrink-0 text-2xs text-ink-4">{timeAgo(l.last_activity_at)}</span>
                      </div>
                      <div className="truncate text-xs text-ink-3">{l.property?.name || "No project"}{l.interest ? ` · ${l.interest}` : ""}</div>
                      <div className="mt-1.5 flex flex-wrap gap-1"><StatusChip status={l.status} />{l.priority && <PriorityChip priority={l.priority} />}<ModeChip mode={l.mode} /></div>
                    </div>
                    <ChevronRight className="mt-2 h-4 w-4 shrink-0 text-ink-4" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            <table className="hidden w-full min-w-[980px] md:table">
              <thead><tr className="border-b border-line">
                {["Lead", "Property", "Status", "Priority", "Owner", "Consent", "Chat", "Last activity"].map((h) => <th key={h} className="th">{h}</th>)}
              </tr></thead>
              <tbody>
                {data.items.map((l: any) => (
                  <tr key={l.id} onClick={() => nav(`/leads/${l.id}`)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && nav(`/leads/${l.id}`)}
                    className="cursor-pointer border-b border-line/60 transition-colors last:border-0 hover:bg-slate-50 focus-visible:bg-slate-50">
                    <td className="td">
                      <div className="flex items-center gap-3">
                        <div className="relative">
                          <Avatar name={l.full_name} />
                          {l.unread_count > 0 && <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-brand-600 ring-2 ring-white" title="Unread messages" />}
                        </div>
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-ink">{l.full_name}</div>
                          <div className="text-xs text-ink-3">{l.phone_masked}</div>
                        </div>
                      </div>
                    </td>
                    <td className="td">
                      <div className="truncate">{l.property?.name || <span className="text-amber-700">Unmapped</span>}</div>
                      <div className="text-xs text-ink-3">{l.interest || l.form?.external_form_id || l.source}</div>
                    </td>
                    <td className="td"><StatusChip status={l.status} /></td>
                    <td className="td"><PriorityChip priority={l.priority} /></td>
                    <td className="td">{l.owner ? <span className="flex items-center gap-2 text-[13px]"><Avatar name={l.owner.name} size="xs" />{l.owner.name}</span> : <span className="text-[13px] text-ink-4">Unassigned</span>}</td>
                    <td className="td"><ConsentChip status={l.consent_status} /></td>
                    <td className="td"><ModeChip mode={l.mode} /></td>
                    <td className="td whitespace-nowrap text-xs text-ink-3">{timeAgo(l.last_activity_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>)}
        </div>
        {data && data.total > PAGE && (
          <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-xs text-ink-3">
            <span>{page * PAGE + 1}–{Math.min((page + 1) * PAGE, data.total)} of {data.total}</span>
            <div className="flex gap-1">
              <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft className="h-3.5 w-3.5" /> Previous</Button>
              <Button size="sm" variant="secondary" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)}>Next <ChevronRight className="h-3.5 w-3.5" /></Button>
            </div>
          </div>
        )}
      </div>
      <AddLead open={adding} onClose={() => setAdding(false)} forms={opts.data?.forms || []} />
    </div>
  );
}

function AddLead({ open, onClose, forms }: { open: boolean; onClose: () => void; forms: any[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const [f, setF] = useState<any>({ full_name: "", phone: "", email: "", city: "", interest: "", form_id: "", whatsapp_consent: false, consent_evidence: "", send_whatsapp: true });
  const m = useMutation({
    mutationFn: () => api("/api/v1/leads", { body: { ...f, email: f.email || null, form_id: f.form_id || null } }),
    onSuccess: (r: any) => {
      qc.invalidateQueries({ queryKey: ["leads"] });
      toast(r.whatsapp_queued ? "Lead added · WhatsApp message on its way" : `Lead added · no WhatsApp sent (${r.reason.replace(/_/g, " ")})`);
      onClose();
      nav(`/leads/${r.id}`);
    },
  });
  const err = (m.error as any)?.fieldErrors || {};
  const up = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal open={open} onClose={onClose} title="Add lead" description="For walk-ins and phone enquiries. Sheet leads are added automatically." width="max-w-xl">
      <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Full name *" error={err.full_name}><input className="input" required value={f.full_name} onChange={up("full_name")} /></Field>
        <Field label="Phone with country code *" error={err.phone}><input className="input" type="tel" required placeholder="+91 98xxx xxxxx" value={f.phone} onChange={up("phone")} /></Field>
        <Field label="Email" error={err.email}><input className="input" type="email" value={f.email} onChange={up("email")} /></Field>
        <Field label="City"><input className="input" value={f.city} onChange={up("city")} /></Field>
        <div className="sm:col-span-2"><Field label="Interested in"><input className="input" value={f.interest} onChange={up("interest")} placeholder="e.g. 3 BHK apartment" /></Field></div>
        <div className="sm:col-span-2"><Field label="Form / property" hint="Decides the property and question flow the WhatsApp assistant uses.">
          <select className="input" value={f.form_id} onChange={up("form_id")}>
            <option value="">None</option>
            {forms.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.external_form_id}){x.mapped ? "" : " · unmapped"}</option>)}
          </select></Field></div>
        <div className="rounded-xl sm:col-span-2 border border-line bg-slate-50 p-3">
          <label className="flex items-center justify-between gap-3 text-sm">
            <span><span className="font-medium text-ink">Customer agreed to WhatsApp messages</span><span className="block text-xs text-ink-3">Required before any automatic message is sent.</span></span>
            <Toggle checked={f.whatsapp_consent} onChange={(v) => setF({ ...f, whatsapp_consent: v })} label="WhatsApp consent" />
          </label>
          {f.whatsapp_consent && (
            <div className="mt-3 space-y-3">
              <Field label="How did they agree? *" error={err.consent_evidence}>
                <input className="input" value={f.consent_evidence} onChange={up("consent_evidence")} placeholder="e.g. Said yes on a call on 23 Nov" /></Field>
              <label className="flex items-center justify-between gap-3 text-sm">
                <span className="text-ink-2">Start the WhatsApp conversation now</span>
                <Toggle checked={f.send_whatsapp} onChange={(v) => setF({ ...f, send_whatsapp: v })} label="Start WhatsApp now" />
              </label>
            </div>
          )}
        </div>
        <div className="sm:col-span-2"><ErrorBox error={m.error} /></div>
        <div className="flex justify-end gap-2 sm:col-span-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={m.isPending}>Add lead</Button>
        </div>
      </form>
    </Modal>
  );
}
