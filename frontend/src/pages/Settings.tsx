import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CheckCircle2, Circle, Plus } from "lucide-react";
import { useState } from "react";
import { Button, Card, Chip, Empty, ErrorBox, Field, Loading, Modal, PageHeader, Tabs, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, timeAgo } from "../lib/format";

export default function SettingsPage() {
  const { user } = useAuth();
  const tabs = user?.role === "admin" ? ["Integrations", "Users and roles", "Audit log"] : ["Integrations", "Audit log"];
  const [tab, setTab] = useState(tabs[0]);
  return (
    <div className="mx-auto max-w-[1440px] p-4 sm:p-6">
      <PageHeader title="Settings" subtitle="Integrations, team and audit. Secrets stay on the server and are never shown here."
        actions={<Tabs value={tab} onChange={setTab} items={tabs.map((t) => ({ value: t, label: t }))} />} />
      {tab === "Integrations" && <Integrations />}
      {tab === "Users and roles" && <Users />}
      {tab === "Audit log" && <Audit />}
    </div>
  );
}

function Check({ ok, label, hint }: { ok: boolean; label: string; hint?: string }) {
  return (
    <div className="flex items-start gap-2 border-b border-slate-50 py-1.5 text-xs last:border-0">
      {ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />}
      <div><div className={ok ? "font-medium" : "text-slate-600"}>{label}</div>{hint && <div className="text-[11px] text-slate-400">{hint}</div>}</div>
    </div>
  );
}

function Integrations() {
  const toast = useToast();
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["settings-status"], queryFn: () => api("/api/v1/settings/status"), refetchInterval: 10000 });
  const [to, setTo] = useState("");
  const test = useMutation({
    mutationFn: () => api("/api/v1/settings/whatsapp/test", { body: { to } }),
    onSuccess: () => toast("hello_world sent — check WhatsApp on that phone"),
    onError: (e: any) => toast(e.message, "error"),
  });
  if (q.isLoading) return <Loading />;
  const g = q.data.google, w = q.data.whatsapp;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Google Sheet (lead source)" action={g.configured ? <Chip className="bg-emerald-50 text-emerald-700 ring-emerald-200">Connected</Chip> : <Chip className="bg-amber-50 text-amber-800 ring-amber-200">Setup pending</Chip>}>
        <Check ok={g.key_file_present} label="Service account key file on the server" hint="secrets/google-service-account.json" />
        <Check ok={!!g.sheet_id} label="Sheet ID configured" hint={g.sheet_id || "GOOGLE_SHEET_ID in .env"} />
        <Check ok={g.last_sync?.ok === true} label="Sheet shared with the service account (read works)" hint={g.service_account || undefined} />
        <div className="mt-2 text-[11px] text-slate-500">Polling every {g.poll_seconds} s · last check {g.last_sync ? timeAgo(g.last_sync.at) : "never"}{g.last_sync?.ok === false && <span className="text-red-600"> · {g.last_sync.error}</span>}</div>
      </Card>
      <Card title="WhatsApp Cloud API" action={w.configured ? <Chip className="bg-emerald-50 text-emerald-700 ring-emerald-200">Sending enabled</Chip> : <Chip className="bg-amber-50 text-amber-800 ring-amber-200">Setup pending</Chip>}>
        <Check ok={!!w.phone_number_id} label="Phone number ID" hint={w.phone_number_id || "secrets/whatsapp.env"} />
        <Check ok={w.token_present} label="Access token (stored on server)" hint="Temporary tokens from the API Setup page expire after ~24 h" />
        <Check ok={w.app_secret_present} label="App secret (verifies webhooks really come from Meta)" />
        <Check ok={!!w.last_webhook_at} label="Webhook receiving replies" hint={w.last_webhook_at ? `Last event ${timeAgo(w.last_webhook_at)}` : `Callback path ${w.webhook_path} via HTTPS tunnel`} />
        <div className="mt-2 text-[11px] text-slate-500">Opening template: <b>{w.opening_template}</b> · Graph API {w.api_version} · {q.data.suppression_count} opted-out numbers</div>
        {user?.role === "admin" && (
          <div className="mt-3 flex gap-2 border-t border-slate-100 pt-3">
            <input className="input" placeholder="Test number e.g. +91 98xxxxxxxx" value={to} onChange={(e) => setTo(e.target.value)} />
            <Button onClick={() => test.mutate()} loading={test.isPending} disabled={!w.configured || !to}>Send test</Button>
          </div>
        )}
      </Card>
    </div>
  );
}

function Users() {
  const qc = useQueryClient();
  const toast = useToast();
  const { user: me } = useAuth();
  const q = useQuery({ queryKey: ["users"], queryFn: () => api("/api/v1/users", { query: { limit: 200 } }) });
  const [adding, setAdding] = useState(false);
  const patch = useMutation({
    mutationFn: ({ id, body }: any) => api(`/api/v1/users/${id}`, { method: "PATCH", body }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); toast("User updated"); },
    onError: (e: any) => toast(e.message, "error"),
  });
  if (q.isLoading) return <Loading />;
  return (
    <>
      <div className="mb-3 flex justify-end"><Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add user</Button></div>
      <div className="card">
        <table className="w-full">
          <thead><tr className="border-b border-slate-100">{["Name", "Email", "Role", "Status", "Last login", ""].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody>{q.data.items.map((u: any) => (
            <tr key={u.id} className="border-b border-slate-50">
              <td className="td font-semibold">{u.full_name}</td><td className="td text-xs">{u.email}</td>
              <td className="td"><select className="input w-32 py-1" value={u.role} disabled={u.id === me?.id} onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value } })}>
                <option value="admin">Admin</option><option value="manager">Manager</option><option value="agent">Agent</option></select></td>
              <td className="td">{u.is_active ? <Chip className="bg-emerald-50 text-emerald-700 ring-emerald-200">Active</Chip> : <Chip className="bg-slate-100 text-slate-500 ring-slate-200">Inactive</Chip>}</td>
              <td className="td text-xs text-slate-500">{u.last_login_at ? timeAgo(u.last_login_at) : "never"}</td>
              <td className="td text-right">{u.id !== me?.id && <Button size="sm" variant="secondary" onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}>{u.is_active ? "Deactivate" : "Activate"}</Button>}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <AddUser open={adding} onClose={() => setAdding(false)} />
    </>
  );
}

function AddUser({ open, onClose }: any) {
  const qc = useQueryClient();
  const [f, setF] = useState({ full_name: "", email: "", role: "agent", password: "" });
  const m = useMutation({ mutationFn: () => api("/api/v1/users", { body: f }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); onClose(); } });
  const err = (m.error as any)?.fieldErrors || {};
  const up = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal open={open} onClose={onClose} title="Add user">
      <div className="space-y-3">
        <Field label="Full name" error={err.full_name}><input className="input" value={f.full_name} onChange={up("full_name")} /></Field>
        <Field label="Email" error={err.email}><input className="input" type="email" value={f.email} onChange={up("email")} /></Field>
        <Field label="Role"><select className="input" value={f.role} onChange={up("role")}><option value="agent">Sales agent</option><option value="manager">Sales manager</option><option value="admin">Admin</option></select></Field>
        <Field label="Temporary password (min 10 characters)" error={err.password}><input className="input" type="password" value={f.password} onChange={up("password")} /></Field>
        <ErrorBox error={m.error} />
        <div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} onClick={() => m.mutate()}>Add user</Button></div>
      </div>
    </Modal>
  );
}

function Audit() {
  const [offset, setOffset] = useState(0);
  const q = useQuery({ queryKey: ["audit", offset], queryFn: () => api("/api/v1/audit", { query: { limit: 50, offset } }) });
  const users = useQuery({ queryKey: ["lead-options"], queryFn: () => api("/api/v1/leads/meta/options") });
  const name = (id: string) => users.data?.users?.find((u: any) => u.id === id)?.name;
  if (q.isLoading) return <Loading />;
  return (
    <div className="card">
      <ErrorBox error={q.error} />
      {q.data.items.length === 0 ? <Empty title="No audit events" /> : (
        <table className="w-full">
          <thead><tr className="border-b border-slate-100">{["Time", "Actor", "Action", "Entity", "Details"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody>{q.data.items.map((e: any) => (
            <tr key={e.id} className="border-b border-slate-50 text-xs">
              <td className="td whitespace-nowrap">{dateTime(e.occurred_at)}</td>
              <td className="td">{e.actor_user_id ? name(e.actor_user_id) || "User" : e.actor_type}</td>
              <td className="td font-mono">{e.action}</td>
              <td className="td text-slate-500">{e.entity_type}{e.entity_id ? ` · ${e.entity_id.slice(0, 8)}` : ""}</td>
              <td className="td max-w-xs truncate font-mono text-[11px] text-slate-500">{Object.keys(e.details || {}).length ? JSON.stringify(e.details) : ""}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
        <span>{q.data.total} events · append-only</span>
        <div className="flex gap-1">
          <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Newer</Button>
          <Button size="sm" variant="secondary" disabled={offset + 50 >= q.data.total} onClick={() => setOffset(offset + 50)}>Older</Button>
        </div>
      </div>
    </div>
  );
}
