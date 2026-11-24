import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Building2, CalendarClock, CheckCircle2, Flame, MessageSquare, Timer, UserPlus, Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Avatar, Card, Empty, ErrorBox, PageHeader, Skeleton, StatCard, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ACTION_LABEL, STATUS_LABEL, timeAgo } from "../lib/format";

const PIPE_COLOR: Record<string, string> = {
  new: "bg-blue-500", contacted: "bg-slate-400", qualified: "bg-emerald-500", site_visit: "bg-violet-500",
  negotiation: "bg-amber-500", won: "bg-green-600", lost: "bg-red-400", nurture: "bg-orange-400",
};

export default function Dashboard() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", days],
    queryFn: () => api("/api/v1/dashboard", { query: { days } }),
    refetchInterval: 15000,
  });

  return (
    <div className="mx-auto max-w-[1440px] p-6">
      <PageHeader title={`Welcome back, ${user?.full_name?.split(" ")[0] || ""}`}
        subtitle={`${new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })} · Lead activity across all properties`}
        actions={<Tabs value={days} onChange={setDays} items={[{ value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }]} />} />
      <ErrorBox error={error} />
      {isLoading || !data ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[108px] rounded-xl" />)}</div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
            <StatCard label="Total leads" value={data.kpis.total} icon={<Users className="h-4 w-4" />} hint={`In the last ${days} days`} onClick={() => nav("/leads")} />
            <StatCard label="New today" value={data.kpis.new_today} icon={<UserPlus className="h-4 w-4" />} hint="Since midnight" onClick={() => nav("/leads?sort=created")} />
            <StatCard label="Qualified" value={data.kpis.total ? `${Math.round((100 * data.kpis.qualified) / data.kpis.total)}%` : "0%"}
              icon={<CheckCircle2 className="h-4 w-4" />} hint={`${data.kpis.qualified} of ${data.kpis.total} leads`} onClick={() => nav("/leads?status=qualified")} />
            <StatCard label="Hot leads" value={data.kpis.hot} tone={data.kpis.hot > 0 ? "red" : "slate"} icon={<Flame className="h-4 w-4" />} hint="Likely to buy soon" onClick={() => nav("/leads?chip=hot")} />
            <StatCard label="Follow-ups" value={data.kpis.followups_due} tone={data.kpis.followups_due > 0 ? "amber" : "slate"} icon={<CalendarClock className="h-4 w-4" />} hint="Due in the next 24h" onClick={() => nav("/followups")} />
            <StatCard label="Response time" value={data.sla.p95 != null ? `${data.sla.p95}s` : "—"} icon={<Timer className="h-4 w-4" />}
              hint={data.sla.measured ? `${data.sla.within_target_pct}% replied in under 10s` : "No replies yet"} />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card title="Lead volume" subtitle="Daily new and qualified leads" className="xl:col-span-2"
              action={<div className="flex items-center gap-4 text-xs text-ink-3">
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-brand-600" />Leads</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-forest" />Qualified</span>
              </div>}>
              <div className="h-52" role="img" aria-label={`Lead trend over ${days} days`}>
                <ResponsiveContainer>
                  <AreaChart data={data.trend} margin={{ left: -24, right: 8, top: 8 }}>
                    <defs>
                      <linearGradient id="gLeads" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22C55E" stopOpacity={0.28} /><stop offset="100%" stopColor="#22C55E" stopOpacity={0} /></linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="0" stroke="#F1F5F9" vertical={false} />
                    <XAxis dataKey="date" tickFormatter={(d) => new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short" })} fontSize={11} tickLine={false} axisLine={false} minTickGap={32} stroke="#94A3B8" />
                    <YAxis allowDecimals={false} fontSize={11} tickLine={false} axisLine={false} stroke="#94A3B8" />
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid #E5E7EB", boxShadow: "0 8px 24px -8px rgba(16,24,40,.15)" }}
                      labelFormatter={(d) => new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })} />
                    <Area type="monotone" dataKey="leads" name="Leads" stroke="#16A34A" strokeWidth={2.5} fill="url(#gLeads)" />
                    <Area type="monotone" dataKey="qualified" name="Qualified" stroke="#0B2A20" strokeWidth={2} strokeDasharray="5 4" fill="transparent" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card title="Response time" subtitle="From new lead to first WhatsApp message" icon={<MessageSquare className="h-4 w-4" />}>
              {data.sla.measured === 0 ? (
                <Empty title="Not enough data yet" hint="Shown once the first WhatsApp messages go out." />
              ) : (
                <div>
                  <div className="flex items-baseline gap-2">
                    <span className="kpi text-4xl font-semibold tracking-tight text-ink">{data.sla.p95}s</span>
                    <span className="text-sm text-ink-3">p95 · target ≤ {data.sla.target_seconds}s</span>
                  </div>
                  <div className="mt-4">
                    <div className="mb-1 flex justify-between text-xs"><span className="text-ink-3">Within target</span><span className="font-semibold">{data.sla.within_target_pct}%</span></div>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                      <div className={clsx("h-full rounded-full", data.sla.within_target_pct >= 90 ? "bg-emerald-500" : data.sla.within_target_pct >= 70 ? "bg-amber-500" : "bg-red-500")} style={{ width: `${data.sla.within_target_pct}%` }} />
                    </div>
                  </div>
                  <dl className="mt-4 grid grid-cols-2 gap-3">
                    {[["Median", `${data.sla.p50}s`], ["Measured", data.sla.measured], ["No consent", data.sla.blocked], ["Failed sends", data.sla.failed_sends]].map(([k, v]) => (
                      <div key={k as string} className="rounded-lg bg-slate-50 px-3 py-2"><dt className="text-xs text-ink-3">{k}</dt><dd className="kpi text-sm font-semibold text-ink">{v}</dd></div>
                    ))}
                  </dl>
                </div>
              )}
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card title="Pipeline" subtitle="Leads by status in this period">
              {data.kpis.total === 0 ? <Empty title="No leads yet" /> : (
                <div className="space-y-2.5">
                  {data.pipeline.map((p: any) => (
                    <Link key={p.status} to={`/leads?status=${p.status}`} className="group block">
                      <div className="mb-1 flex justify-between text-xs"><span className="font-medium text-ink-2 group-hover:text-ink">{STATUS_LABEL[p.status]}</span><span className="kpi text-ink-3">{p.count}</span></div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100"><div className={clsx("h-full rounded-full", PIPE_COLOR[p.status])} style={{ width: `${data.kpis.total ? (100 * p.count) / data.kpis.total : 0}%` }} /></div>
                    </Link>
                  ))}
                  <div className="flex gap-2 pt-2">
                    {(["hot", "warm", "cold"] as const).map((k) => (
                      <Link key={k} to={`/leads?priority=${k}`} className={clsx("flex-1 rounded-lg px-3 py-2 text-center transition-colors",
                        k === "hot" ? "bg-red-50 hover:bg-red-100" : k === "warm" ? "bg-amber-50 hover:bg-amber-100" : "bg-blue-50 hover:bg-blue-100")}>
                        <div className={clsx("kpi text-lg font-semibold", k === "hot" ? "text-red-700" : k === "warm" ? "text-amber-800" : "text-blue-700")}>{data.priority[k]}</div>
                        <div className="text-2xs font-medium capitalize text-ink-3">{k}</div>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </Card>

            <Card title="Performance" subtitle="By property and agent" bodyClass="p-0" icon={<Building2 className="h-4 w-4" />}>
              {data.by_property.length === 0 ? <Empty title="No leads yet" /> : (
                <table className="w-full">
                  <thead><tr className="border-b border-line"><th className="th">Property</th><th className="th text-right">Leads</th><th className="th text-right">Qualified</th><th className="th text-right">Hot</th></tr></thead>
                  <tbody>{data.by_property.map((p: any) => (
                    <tr key={p.property} className="border-b border-line/60 last:border-0">
                      <td className="td font-medium">{p.property}</td><td className="td text-right">{p.leads}</td>
                      <td className="td text-right">{p.leads ? Math.round((100 * p.qualified) / p.leads) : 0}%</td><td className="td text-right font-semibold text-red-600">{p.hot}</td>
                    </tr>))}</tbody>
                </table>
              )}
              {data.by_agent.length > 0 && (
                <div className="border-t border-line p-4">
                  <div className="mb-2 text-xs font-medium text-ink-3">Agents</div>
                  <div className="space-y-2">{data.by_agent.map((a: any) => (
                    <div key={a.agent?.id} className="flex items-center gap-2.5 text-sm">
                      <Avatar name={a.agent?.name} size="xs" /><span className="flex-1 font-medium">{a.agent?.name}</span>
                      <span className="text-xs text-ink-3">{a.open} open · {a.qualified} qualified · {a.won} won</span>
                    </div>))}</div>
                </div>
              )}
            </Card>

            <Card title="Recent activity" bodyClass="px-4 py-2">
              {data.activity.length === 0 ? <Empty title="Nothing yet" /> : (
                <ol className="relative">
                  {data.activity.map((a: any, i: number) => (
                    <li key={i} className="relative flex gap-3 py-2.5">
                      {i < data.activity.length - 1 && <span className="absolute left-[11px] top-8 h-[calc(100%-20px)] w-px bg-line" aria-hidden />}
                      <span className={clsx("mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ring-4 ring-white",
                        a.action === "consent.opt_out" ? "bg-red-100" : a.action === "lead.qualified" ? "bg-emerald-100" : a.action.startsWith("conversation") ? "bg-violet-100" : "bg-brand-50")}>
                        <span className={clsx("h-2 w-2 rounded-full", a.action === "consent.opt_out" ? "bg-red-500" : a.action === "lead.qualified" ? "bg-emerald-500" : a.action.startsWith("conversation") ? "bg-violet-500" : "bg-brand-600")} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm">
                          {a.lead_id ? <Link className="font-semibold text-ink hover:underline" to={`/leads/${a.lead_id}`}>{a.lead_name || "Lead"}</Link> : <span className="font-semibold">System</span>}
                          <span className="text-ink-3"> · {ACTION_LABEL[a.action] || a.action}</span>
                        </div>
                        <div className="text-xs text-ink-3">
                          {a.action === "lead.qualified" && a.details?.priority && `${a.details.priority.toUpperCase()} · `}
                          {a.action === "import.batch_completed" && `${a.details.imported} new · ${a.details.duplicates} duplicates · ${a.details.errors} errors · `}
                          {a.action === "lead.status_change" && `→ ${STATUS_LABEL[a.details.to] || a.details.to} · `}
                          {timeAgo(a.at)}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
