import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { RefreshCw, Sheet } from "lucide-react";
import { useState } from "react";
import { Button, Card, Chip, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, timeAgo } from "../lib/format";

const STATUS: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  completed_with_errors: "bg-amber-50 text-amber-800 ring-amber-200",
  failed: "bg-red-50 text-red-700 ring-red-200",
  running: "bg-blue-50 text-blue-700 ring-blue-200",
};

export default function Imports() {
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
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
    <div className="mx-auto max-w-[1440px] p-6">
      <PageHeader title="Import monitor" subtitle={`Your Google Sheet is checked every ${s.poll_seconds} seconds. Re-reading is always safe — no duplicate leads or messages.`} />
      <ErrorBox error={q.error} />
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

      <Card title="Import batches" bodyClass="p-0" className="mb-4">
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
        <Card title={`Row errors · batch #${batch}`} action={<span className="text-[11px] text-slate-500">valid rows are never blocked by invalid rows</span>} bodyClass="p-0">
          {errors.isLoading ? <Loading /> : errors.data.items.length === 0 ? <Empty title="No row errors in this batch" /> : (
            <table className="w-full"><thead><tr className="border-b border-slate-100">{["Row", "Field", "Problem", "Suggested action"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
              <tbody>{errors.data.items.map((e: any, i: number) => (
                <tr key={i} className="border-b border-slate-50"><td className="td">Row {e.row_number}</td><td className="td font-mono text-xs">{e.field}</td><td className="td">{e.message}</td>
                  <td className="td text-xs text-slate-500">{e.code === "invalid_phone" ? "Fix the number in the sheet; it is re-read automatically" : e.code === "missing_name" ? "Add the name in the sheet" : "Fix the row in the sheet"}</td></tr>
              ))}</tbody></table>
          )}
        </Card>
      )}
    </div>
  );
}
