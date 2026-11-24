import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CalendarCheck, Check } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Avatar, Empty, ErrorBox, Loading, PageHeader, PriorityChip, StatusChip, Tabs, useToast } from "../components/ui";
import { api } from "../lib/api";
import { isManager, useAuth } from "../lib/auth";
import { dateTime } from "../lib/format";

function group(items: any[]) {
  const now = new Date();
  const endToday = new Date(now); endToday.setHours(23, 59, 59, 999);
  const g: Record<string, any[]> = { Overdue: [], Today: [], Upcoming: [] };
  for (const f of items) {
    const d = new Date(f.due_at);
    (d < now ? g.Overdue : d <= endToday ? g.Today : g.Upcoming).push(f);
  }
  return g;
}

export default function FollowUps() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [scope, setScope] = useState<"mine" | "all">(isManager(user) ? "all" : "mine");
  const [status, setStatus] = useState<"open" | "done">("open");
  const q = useQuery({ queryKey: ["followups", scope, status], queryFn: () => api("/api/v1/followups", { query: { scope, status } }), refetchInterval: 10000 });
  const done = useMutation({
    mutationFn: (id: number) => api(`/api/v1/followups/${id}/done`, { body: {} }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["followups"] }); qc.invalidateQueries({ queryKey: ["nav-counts"] }); toast("Marked as done"); },
  });
  const sections = status === "open" ? group(q.data?.items || []) : { Completed: q.data?.items || [] };

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-6">
      <PageHeader title="Follow-ups" subtitle="Created automatically when a lead qualifies or asks for a person — plus any you schedule."
        actions={<>
          {isManager(user) && <Tabs value={scope} onChange={setScope} items={[{ value: "mine", label: "Mine" }, { value: "all", label: "Everyone" }]} />}
          <Tabs value={status} onChange={setStatus} items={[{ value: "open", label: "Open" }, { value: "done", label: "Done" }]} />
        </>} />
      <ErrorBox error={q.error} />
      {q.isLoading ? <div className="card"><Loading /></div> : q.data.items.length === 0 ? (
        <div className="card"><Empty title={status === "open" ? "You're all caught up" : "Nothing completed yet"} icon={<CalendarCheck className="h-5 w-5" />} /></div>
      ) : (
        <div className="space-y-6">
          {Object.entries(sections).filter(([, v]) => v.length).map(([name, list]) => (
            <section key={name}>
              <h2 className={clsx("mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide", name === "Overdue" ? "text-red-600" : "text-ink-3")}>
                {name}<span className="rounded-md bg-slate-100 px-1.5 text-ink-3">{list.length}</span></h2>
              <ul className="card divide-y divide-line/70">
                {list.map((f: any) => (
                  <li key={f.id} className="flex items-center gap-4 px-4 py-3">
                    <button aria-label="Mark done" disabled={f.status === "done" || done.isPending} onClick={() => done.mutate(f.id)}
                      className={clsx("flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors",
                        f.status === "done" ? "border-brand-700 bg-brand-700 text-white" : "border-line-strong hover:border-brand-600 hover:bg-brand-50")}>
                      {f.status === "done" && <Check className="h-3.5 w-3.5" />}
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className={clsx("truncate text-sm", f.status === "done" ? "text-ink-4 line-through" : "font-medium text-ink")}>{f.note || "Follow up"}</div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-ink-3">
                        <Link to={`/leads/${f.lead.id}`} className="font-semibold text-ink-2 hover:underline">{f.lead.full_name}</Link>
                        {f.lead.property && <span>· {f.lead.property}</span>}
                        <span className={clsx(f.overdue && "font-semibold text-red-600")}>· {dateTime(f.due_at)}</span>
                      </div>
                    </div>
                    <div className="hidden items-center gap-1.5 sm:flex"><PriorityChip priority={f.lead.priority} /><StatusChip status={f.lead.status} /></div>
                    <span title={f.assigned_to?.name || "Unassigned"}><Avatar name={f.assigned_to?.name || "?"} size="xs" /></span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
