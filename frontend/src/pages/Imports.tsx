import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { RefreshCw, Sheet } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button, Card, Chip, Empty, ErrorBox, Loading, PageHeader, Tabs, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, timeAgo } from "../lib/format";

const STATUS: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  completed_with_errors: "bg-amber-50 text-amber-800 ring-amber-200",
  failed: "bg-red-50 text-red-700 ring-red-200",
  running: "bg-blue-50 text-blue-700 ring-blue-200",
};

const OUTCOME: Record<string, [string, string]> = {
  messaged: ["Messaged", "bg-emerald-50 text-emerald-700"],
  failed: ["Failed", "bg-red-50 text-red-700"],
  not_messaged: ["Not messaged", "bg-amber-50 text-amber-800"],
  waiting: ["Waiting", "bg-sky-50 text-sky-700"],
  not_imported: ["Not imported", "bg-red-50 text-red-700"],
  duplicate: ["Duplicate", "bg-slate-100 text-slate-600"],
};

/** Every sheet row, matched to the CRM: messaged or not, delivery status, and why not. */
function SheetRows() {
  const [filter, setFilter] = useState<string>("");
  const r = useQuery({ queryKey: ["sheet-report"], queryFn: () => api("/api/v1/imports/sheet-report"), refetchInterval: 15000 });
  if (r.isLoading) return <Loading rows={6} />;
  if (r.error) return <ErrorBox error={r.error} />;
  const d = r.data;
  const items = d.items.filter((i: any) => !filter || i.outcome === filter);
  const chips: [string, string, number][] = [["", "All rows", d.total], ...Object.entries(OUTCOME)
    .map(([k, [label]]) => [k, label, d.summary[k]] as [string, string, number]).filter(([, , n]) => n > 0)];
  return (
    <div className="space-y-3">
      {d.error && <ErrorBox error={{ message: `Could not read the sheet: ${d.error}` }} />}
      <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0">
        {chips.map(([k, label, n]) => (
          <button key={k} onClick={() => setFilter(k)} aria-pressed={filter === k}
            className={clsx("inline-flex h-9 shrink-0 items-center gap-2 rounded-full border px-3.5 text-sm font-medium transition-colors",
              filter === k ? "border-brand-700 bg-brand-700 text-white" : "border-line bg-white text-ink-2 hover:bg-slate-50")}>
            {label}<span className={clsx("rounded-full px-1.5 text-xs font-semibold", filter === k ? "bg-white/20" : "bg-slate-100 text-ink-3")}>{n}</span>
          </button>
        ))}
      </div>
      <div className="card overflow-hidden">
        {items.length === 0 ? <Empty title={d.total ? "No rows with this result" : "The sheet has no lead rows yet"} /> : (<>
          {/* Phone: one card per row */}
          <ul className="divide-y divide-line/60 md:hidden">
            {items.map((i: any) => <RowCard key={i.row} i={i} />)}
          </ul>
          <table className="hidden w-full md:table">
            <thead><tr className="border-b border-line">{["Row", "Lead", "Property / looking for", "Result", "Why / what happened", "First message", ""].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody>{items.map((i: any) => (
              <tr key={i.row} className="border-b border-line/60 align-top last:border-0">
                <td className="td text-xs text-ink-3">#{i.row}</td>
                <td className="td"><div className="font-semibold text-ink">{i.name || "—"}</div><div className="text-xs text-ink-3">{i.phone}</div></td>
                <td className="td"><div>{i.property || "—"}</div><div className="text-xs text-ink-3">{i.looking_for || ""}</div></td>
                <td className="td"><Chip className={OUTCOME[i.outcome][1]}>{OUTCOME[i.outcome][0]}</Chip></td>
                <td className="td max-w-[360px] text-xs text-ink-2">{i.reason}</td>
                <td className="td whitespace-nowrap text-xs text-ink-3">{i.message_status ? <><b className="text-ink-2">{i.message_status}</b><div>{dateTime(i.message_at)}</div></> : "—"}</td>
                <td className="td whitespace-nowrap text-right">
                  {i.conversation_id && i.message_status && <Link to={`/conversations/${i.conversation_id}`} className="mr-3 text-xs font-semibold text-brand-700 hover:underline">Chat</Link>}
                  {i.lead_id && <Link to={`/leads/${i.lead_id}`} className="text-xs font-semibold text-brand-700 hover:underline">Lead</Link>}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </>)}
      </div>
      <p className="text-xs text-ink-3">Updated every 15 seconds{d.tab ? ` from the “${d.tab}” tab` : ""}. Newest rows first.</p>
    </div>
  );
}

function RowCard({ i }: { i: any }) {
  return (
    <li className="px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-semibold text-ink">{i.name || "—"} <span className="text-xs font-normal text-ink-4">· row {i.row}</span></div>
          <div className="truncate text-xs text-ink-3">{i.phone}{i.property ? ` · ${i.property}` : ""}{i.looking_for ? ` · ${i.looking_for}` : ""}</div>
        </div>
        <Chip className={clsx("shrink-0", OUTCOME[i.outcome][1])}>{OUTCOME[i.outcome][0]}</Chip>
      </div>
      <div className="mt-1.5 text-sm text-ink-2">{i.reason}</div>
      {(i.message_status || i.lead_id) && (
        <div className="mt-2 flex items-center gap-4 text-xs">
          {i.message_status && <span className="text-ink-3">First message: <b className="text-ink-2">{i.message_status}</b> · {timeAgo(i.message_at)}</span>}
          <span className="ml-auto flex gap-4">
            {i.conversation_id && i.message_status && <Link to={`/conversations/${i.conversation_id}`} className="font-semibold text-brand-700">Chat</Link>}
            {i.lead_id && <Link to={`/leads/${i.lead_id}`} className="font-semibold text-brand-700">Lead</Link>}
          </span>
        </div>
      )}
    </li>
  );
}

export default function Imports() {
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const [view, setView] = useState<"rows" | "history">("rows");
  const [batch, setBatch] = useState<number | null>(null);
  const q = useQuery({ queryKey: ["imports"], queryFn: () => api("/api/v1/imports"), refetchInterval: 10000 });
  const errors = useQuery({ queryKey: ["import-errors", batch], queryFn: () => api(`/api/v1/imports/${batch}/errors`), enabled: batch !== null });
  const sync = useMutation({
    mutationFn: () => api("/api/v1/imports/sync", { body: {} }),
    onSuccess: (r: any) => {
      qc.invalidateQueries({ queryKey: ["imports"] });
      if (r.batch) { setBatch(r.batch.id); toast(r.batch.status === "failed" ? `Sync failed: ${r.batch.error_message}` : `Sync done: ${r.batch.rows_imported} new, ${r.batch.rows_duplicate} already imported, ${r.batch.rows_error} errors`, r.batch.status === "failed" ? "error" : "ok"); }
      else toast(r.message);
    },
    onError: (e: any) => toast(e.message, "error"),
  });
  if (q.isLoading) return <Loading />;
  const s = q.data.source;
  const last = s.last_sync;

  return (
    <div className="mx-auto max-w-[1440px] p-4 sm:p-6">
      <PageHeader title="Sheet & imports" subtitle="Every enquiry in your Google Sheet: was it messaged on WhatsApp, and if not, why." />
      <ErrorBox error={q.error} />
      <Tabs value={view} onChange={setView} className="mb-4"
        items={[{ value: "rows", label: "Sheet rows" }, { value: "history", label: "Import history" }]} />
      {view === "rows" && <SheetRows />}
      {view === "history" && <>
      <div className="mb-4 grid gap-3 lg:grid-cols-[1.4fr_repeat(4,1fr)]">
        <div className="card flex items-center gap-3 px-4 py-3">
          <Sheet className="h-8 w-8 shrink-0 text-emerald-600" />
          <div className="min-w-0 flex-1 text-xs">
            <div className="font-semibold text-navy">Google Sheet {s.configured ? (last?.ok === false ? <Chip className="ml-1 bg-red-50 text-red-700 ring-red-200">Error</Chip> : <Chip className="ml-1 bg-emerald-50 text-emerald-700 ring-emerald-200">Connected</Chip>) : <Chip className="ml-1 bg-amber-50 text-amber-800 ring-amber-200">Not set up</Chip>}</div>
            {s.sheet_url && <a href={s.sheet_url} target="_blank" rel="noreferrer" className="block truncate text-teal-700 hover:underline">{s.sheet_id}</a>}
            <div className="text-slate-500">Last check {last ? timeAgo(last.at) : "never"}{last?.tab && ` · tab "${last.tab}" · ${last.rows} rows`}</div>
            {last?.ok === false && <div className="text-red-600">{last.error}</div>}
          </div>
          {user?.role === "admin" && <Button size="sm" onClick={() => sync.mutate()} loading={sync.isPending}><RefreshCw className="h-3.5 w-3.5" /> Sync now</Button>}
        </div>
        {[["Imports (24 h)", q.data.last_24h.batches, "text-navy"], ["Leads imported", q.data.last_24h.imported, "text-emerald-600"], ["Duplicates skipped", q.data.last_24h.duplicates, "text-amber-600"], ["Row errors", q.data.last_24h.errors, "text-red-600"]].map(([l, v, c]) => (
          <div key={l as string} className="card px-4 py-3"><div className="text-[11px] text-slate-500">{l}</div><div className={clsx("text-2xl font-bold", c as string)}>{v}</div></div>
        ))}
      </div>

      <Card title="Import batches" bodyClass="overflow-x-auto p-0" className="mb-4">
        {q.data.batches.length === 0 ? <Empty title="No imports yet" hint="An import batch is recorded each time new rows are found (or when you press Sync now)." /> : (
          <table className="w-full">
            <thead><tr className="border-b border-slate-100">{["Batch", "Started", "By", "Rows", "Imported", "Dupes", "Errors", "Status", ""].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody>{q.data.batches.map((b: any) => (
              <tr key={b.id} className={clsx("border-b border-slate-50", batch === b.id && "bg-teal-50/50")}>
                <td className="td font-semibold">#{b.id}</td><td className="td text-xs">{dateTime(b.started_at)}</td><td className="td text-xs text-slate-500">{b.triggered_by}</td>
                <td className="td">{b.rows_total}</td><td className="td text-emerald-700">{b.rows_imported}</td><td className="td text-amber-700">{b.rows_duplicate}</td><td className="td text-red-600">{b.rows_error}</td>
                <td className="td"><Chip className={STATUS[b.status]}>{b.status.replace(/_/g, " ")}</Chip>{b.error_message && <div className="mt-0.5 text-[11px] text-red-600">{b.error_message}</div>}</td>
                <td className="td text-right"><Button size="sm" variant="secondary" onClick={() => setBatch(b.id)}>View</Button></td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </Card>

      {batch !== null && (
        <Card title={`Row errors · batch #${batch}`} action={<span className="hidden text-[11px] text-slate-500 sm:inline">valid rows are never blocked by invalid rows</span>} bodyClass="overflow-x-auto p-0">
          {errors.isLoading ? <Loading /> : errors.data.items.length === 0 ? <Empty title="No row errors in this batch" /> : (
            <table className="w-full"><thead><tr className="border-b border-slate-100">{["Row", "Field", "Problem", "Suggested action"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
              <tbody>{errors.data.items.map((e: any, i: number) => (
                <tr key={i} className="border-b border-slate-50"><td className="td">Row {e.row_number}</td><td className="td font-mono text-xs">{e.field}</td><td className="td">{e.message}</td>
                  <td className="td text-xs text-slate-500">{e.code === "invalid_phone" ? "Fix the number in the sheet; it is re-read automatically" : e.code === "missing_name" ? "Add the name in the sheet" : "Fix the row in the sheet"}</td></tr>
              ))}</tbody></table>
          )}
        </Card>
      )}
      </>}
    </div>
  );
}
