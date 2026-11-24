import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Building2, Plus } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Button, Card, Empty, ErrorBox, Field, Loading, PageHeader, Toggle, useToast } from "../components/ui";
import { api } from "../lib/api";
import { inr } from "../lib/format";

const BLANK = { name: "", property_type: "apartment", location: "", price_min: "", price_max: "", possession: "", description: "", brochure_url: "", is_active: true };

export default function Properties() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["properties"], queryFn: () => api("/api/v1/properties") });
  const [selected, setSelected] = useState<string | "new" | null>(null);
  const [f, setF] = useState<any>(BLANK);
  const items = q.data?.items || [];
  const current = items.find((p: any) => p.id === selected);

  useEffect(() => { if (!selected && items.length) setSelected(items[0].id); }, [items, selected]);
  useEffect(() => {
    if (selected === "new") setF(BLANK);
    else if (current) setF({ ...current, price_min: current.price_min ?? "", price_max: current.price_max ?? "", possession: current.possession ?? "", brochure_url: current.brochure_url ?? "" });
  }, [selected, current?.id, current?.updated_at]);

  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, price_min: f.price_min === "" ? null : Number(f.price_min), price_max: f.price_max === "" ? null : Number(f.price_max),
        possession: f.possession || null, brochure_url: f.brochure_url || null };
      delete body.id; delete body.lead_count; delete body.forms; delete body.updated_at;
      return selected === "new" ? api("/api/v1/properties", { body }) : api(`/api/v1/properties/${selected}`, { method: "PUT", body });
    },
    onSuccess: (p: any) => { qc.invalidateQueries({ queryKey: ["properties"] }); setSelected(p.id); toast("Property saved"); },
  });
  const err = (save.error as any)?.fieldErrors || {};
  const up = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });

  return (
    <div className="mx-auto max-w-[1440px] p-6">
      <PageHeader title="Properties" subtitle="Verified details the WhatsApp assistant shares with customers. Starting price is also used in lead scoring."
        actions={<Button onClick={() => setSelected("new")}><Plus className="h-4 w-4" /> Add property</Button>} />
      {q.isLoading ? <Loading /> : (
        <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
          <div className="card overflow-hidden">
            {items.length === 0 && selected !== "new" && <Empty title="No properties yet" hint="Add the projects you advertise on Meta." />}
            {items.map((p: any) => (
              <button key={p.id} onClick={() => setSelected(p.id)} aria-current={selected === p.id}
                className={clsx("flex w-full items-center gap-3 border-b border-line/60 px-4 py-3 text-left transition-colors last:border-0", selected === p.id ? "bg-brand-50/70" : "hover:bg-slate-50")}>
                <span className={clsx("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", selected === p.id ? "bg-brand-700 text-white" : "bg-slate-100 text-ink-3")}><Building2 className="h-4 w-4" /></span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-ink">{p.name} {!p.is_active && <span className="text-xs font-normal text-ink-4">(inactive)</span>}</span>
                  <span className="block text-xs capitalize text-ink-3">{p.property_type} · {p.lead_count} leads · {p.forms.length} forms</span>
                </span>
              </button>
            ))}
          </div>
          {selected && (
            <Card title={selected === "new" ? "New property" : f.name}>
              <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="grid gap-3 md:grid-cols-2">
                <Field label="Name" error={err.name}><input className="input" required value={f.name} onChange={up("name")} /></Field>
                <Field label="Type"><select className="input" value={f.property_type} onChange={up("property_type")}>
                  {["apartment", "plot", "villa", "commercial"].map((t) => <option key={t} value={t}>{t[0].toUpperCase() + t.slice(1)}</option>)}</select></Field>
                <div className="md:col-span-2"><Field label="Location"><input className="input" value={f.location} onChange={up("location")} /></Field></div>
                <Field label="Starting price (₹)" error={err.price_min} hint={f.price_min ? inr(Number(f.price_min)) : "e.g. 6500000 for ₹65 L"}>
                  <input className="input" type="number" min={0} value={f.price_min} onChange={up("price_min")} /></Field>
                <Field label="Top price (₹)" error={err.price_max} hint={f.price_max ? inr(Number(f.price_max)) : undefined}>
                  <input className="input" type="number" min={0} value={f.price_max} onChange={up("price_max")} /></Field>
                <Field label="Possession"><input className="input" value={f.possession} onChange={up("possession")} placeholder="Ready to move / Dec 2027" /></Field>
                <Field label="Brochure link"><input className="input" value={f.brochure_url} onChange={up("brochure_url")} placeholder="https://…" /></Field>
                <div className="md:col-span-2"><Field label="Description (for agents)"><textarea className="input min-h-[90px]" value={f.description} onChange={up("description")} /></Field></div>
                <label className="flex items-center gap-2 text-xs"><Toggle checked={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} /> Active</label>
                {current?.forms?.length > 0 && (
                  <div className="md:col-span-2 text-xs text-slate-600"><span className="label">Meta forms mapped here</span>{current.forms.map((x: any) => `${x.name} (${x.external_form_id})`).join(", ")}</div>
                )}
                <div className="md:col-span-2"><ErrorBox error={save.error} /></div>
                <div className="md:col-span-2 flex justify-end"><Button type="submit" loading={save.isPending}>Save property</Button></div>
              </form>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
