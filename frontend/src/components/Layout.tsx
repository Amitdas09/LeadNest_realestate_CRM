import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Building2, CalendarClock, Download, Inbox, LayoutDashboard, LogOut, MessageSquare, Plus, Search, Settings, Workflow } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { isManager, useAuth } from "../lib/auth";
import { BRAND, LogoMark, Wordmark } from "../lib/brand";
import { timeAgo } from "../lib/format";

const TITLES: Record<string, string> = {
  "/": "Dashboard", "/leads": "Leads", "/conversations": "Conversations", "/followups": "Follow-ups",
  "/properties": "Properties", "/forms": "Forms & flows", "/imports": "Import monitor", "/settings": "Settings",
};

function title(path: string): { label: string; parent?: { label: string; to: string } } {
  if (/^\/leads\/[^/]+$/.test(path)) return { label: "Lead profile", parent: { label: "Leads", to: "/leads" } };
  if (path.startsWith("/conversations")) return { label: "Conversations" };
  return { label: TITLES[path] || "LeadFlow" };
}


function RailItem({ to, label, icon: Icon, end, badge }: any) {
  return (
    <NavLink to={to} end={end} title={label}
      className={({ isActive }) => clsx("group relative flex w-full flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 text-[11px] font-medium transition-colors duration-150",
        isActive ? "text-white" : "text-sidebar-fg hover:text-white")}>
      {({ isActive }: { isActive: boolean }) => (
        <>
          <span className={clsx("relative flex h-8 w-8 items-center justify-center rounded-lg transition-colors duration-150",
            isActive ? "bg-white/15 text-white ring-1 ring-white/20" : "group-hover:bg-white/10")}>
            <Icon size={18} strokeWidth={isActive ? 2.2 : 1.8} aria-hidden />
            {badge > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-500 px-1 text-[10px] font-bold leading-none text-white ring-2 ring-forest">
                {badge > 99 ? "99+" : badge}
              </span>
            )}
          </span>
          <span className="max-w-full truncate leading-tight">{label}</span>
        </>
      )}
    </NavLink>
  );
}

function StatusPill({ ok, label, detail, to }: { ok: boolean | null; label: string; detail?: string; to: string }) {
  return (
    <Link to={to} className={clsx("hidden items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors lg:flex",
      ok ? "border-brand-200 bg-brand-50 text-brand-800 hover:bg-brand-100" : ok === false ? "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100" : "border-line bg-white text-ink-3")}>
      <span className={clsx("h-1.5 w-1.5 rounded-full", ok ? "bg-brand-500" : ok === false ? "bg-amber-500" : "bg-ink-4")} aria-hidden />
      {label}{detail && <span className="font-normal opacity-75">· {detail}</span>}
    </Link>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [q, setQ] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const manager = isManager(user);

  const counts = useQuery({ queryKey: ["nav-counts"], queryFn: () => api("/api/v1/leads", { query: { limit: 1 } }), refetchInterval: 10000 });
  const status = useQuery({ queryKey: ["settings-status"], queryFn: () => api("/api/v1/settings/status"), refetchInterval: 30000, enabled: manager });
  const chips = counts.data?.chips || {};
  const wa = status.data?.whatsapp;
  const sync = status.data?.google?.last_sync;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) { e.preventDefault(); searchRef.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const search = (e: FormEvent) => { e.preventDefault(); nav(`/leads?q=${encodeURIComponent(q)}`); };

  const items = [
    { to: "/", end: true, label: "Home", icon: LayoutDashboard },
    { to: "/leads", label: "Leads", icon: Inbox, badge: chips.needs_review },
    { to: "/conversations", label: "Chats", icon: MessageSquare, badge: chips.unread },
    { to: "/followups", label: "Tasks", icon: CalendarClock, badge: chips.followup_due },
  ];
  const setup = manager ? [
    { to: "/properties", label: "Properties", icon: Building2 },
    { to: "/forms", label: "Flows", icon: Workflow },
    { to: "/imports", label: "Imports", icon: Download },
    { to: "/settings", label: "Settings", icon: Settings },
  ] : [];
  const t = title(pathname);
  const initials = (user?.full_name || "?").split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2);
  const fullBleed = pathname.startsWith("/conversations");

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2">Skip to content</a>

      <aside className="flex h-full w-[80px] shrink-0 flex-col items-center bg-forest px-2 py-3" aria-label="Main navigation">
        <Link to="/" aria-label={`${BRAND.name} home`} className="mb-3 shrink-0"><LogoMark /></Link>
        <div className="scroll-thin flex min-h-0 w-full flex-1 flex-col items-center overflow-y-auto">
          <nav className="flex w-full flex-col gap-0.5">{items.map((i) => <RailItem key={i.to} {...i} />)}</nav>
          {setup.length > 0 && (
            <>
              <div className="my-2 h-px w-8 shrink-0 bg-white/10" />
              <nav className="flex w-full flex-col gap-0.5" aria-label="Setup">{setup.map((i) => <RailItem key={i.to} {...i} />)}</nav>
            </>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-center gap-1.5 border-t border-white/10 pt-3">
          <div title={`${user?.full_name} · ${user?.role}`} className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-xs font-semibold text-white">{initials}</div>
          <button onClick={logout} aria-label="Sign out" title="Sign out" className="rounded-md p-1.5 text-sidebar-fg transition-colors hover:bg-white/10 hover:text-white"><LogOut size={15} /></button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="z-20 flex h-14 shrink-0 items-center gap-4 border-b border-line bg-white px-6">
          <div className="min-w-0 flex-1">
            {t.parent ? (
              <Link to={t.parent.to} className="inline-flex items-center gap-1 text-sm font-medium text-ink-3 transition-colors hover:text-ink">← Back to {t.parent.label}</Link>
            ) : (
              <div className="flex items-center gap-2.5">
                <Wordmark className="text-[17px]" />
                <span className="hidden h-4 w-px bg-line-strong sm:block" aria-hidden />
                <span className="hidden text-[13px] text-ink-3 sm:inline">{BRAND.tagline}</span>
                <span className="sr-only">· {t.label}</span>
              </div>
            )}
          </div>
          {manager && (
            <div className="flex items-center gap-2">
              <StatusPill to="/settings" ok={wa ? wa.configured && !!wa.last_webhook_at : null} label={wa?.configured ? "WhatsApp connected" : "WhatsApp setup"} />
              <StatusPill to="/imports" ok={sync ? sync.ok : null} label="Sheet sync" detail={sync ? timeAgo(sync.at) : undefined} />
            </div>
          )}
          <form onSubmit={search} role="search" className="relative w-56 xl:w-72">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-4" aria-hidden />
            <input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search leads" placeholder="Search leads" className="input bg-canvas pl-9 pr-9" />
            <kbd className="pointer-events-none absolute right-3 top-2 rounded border border-line bg-white px-1.5 font-mono text-2xs text-ink-4">/</kbd>
          </form>
          <button onClick={() => nav("/leads?add=1")} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-700 px-3.5 text-sm font-semibold text-white shadow-xs transition-colors hover:bg-brand-800">
            <Plus className="h-4 w-4" /> Add lead
          </button>
        </header>
        <main id="main" className={clsx("scroll-thin min-h-0 flex-1", fullBleed ? "overflow-hidden" : "overflow-auto")}><Outlet /></main>
      </div>
    </div>
  );
}
