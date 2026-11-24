import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, Building2, CalendarClock, ChevronRight, Download, Inbox, LayoutDashboard, LogOut, Menu, MessageSquare, Plus, Search, Settings, Workflow, X } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { isManager, useAuth } from "../lib/auth";
import { BRAND, LogoMark, Wordmark } from "../lib/brand";
import { timeAgo } from "../lib/format";

const TITLES: Record<string, string> = {
  "/": "Dashboard", "/leads": "Leads", "/conversations": "Chats", "/followups": "Follow-ups",
  "/properties": "Properties", "/forms": "Forms & flows", "/imports": "Sheet & imports", "/settings": "Settings",
};

function title(path: string): { label: string; parent?: { label: string; to: string } } {
  if (/^\/leads\/[^/]+$/.test(path)) return { label: "Lead profile", parent: { label: "Leads", to: "/leads" } };
  if (path.startsWith("/conversations")) return { label: "Chats" };
  return { label: TITLES[path] || BRAND.name };
}

const Badge = ({ n, ring = "ring-forest" }: { n?: number; ring?: string }) =>
  n && n > 0 ? (
    <span className={clsx("absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-500 px-1 text-[10px] font-bold leading-none text-white ring-2", ring)}>
      {n > 99 ? "99+" : n}
    </span>
  ) : null;

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
            <Badge n={badge} />
          </span>
          <span className="max-w-full truncate leading-tight">{label}</span>
        </>
      )}
    </NavLink>
  );
}

/** Phone bottom tab. */
function TabItem({ to, label, icon: Icon, end, badge }: any) {
  return (
    <NavLink to={to} end={end}
      className={({ isActive }) => clsx("flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[11px] font-medium",
        isActive ? "text-brand-700" : "text-ink-3")}>
      {({ isActive }: { isActive: boolean }) => (
        <>
          <span className={clsx("relative flex h-7 w-12 items-center justify-center rounded-full transition-colors", isActive && "bg-brand-50")}>
            <Icon size={20} strokeWidth={isActive ? 2.3 : 1.8} aria-hidden />
            <Badge n={badge} ring="ring-white" />
          </span>
          <span className="truncate">{label}</span>
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
  const [searchOpen, setSearchOpen] = useState(false); // phone: search bar under the header
  const [moreOpen, setMoreOpen] = useState(false); // phone: "More" sheet
  const searchRef = useRef<HTMLInputElement>(null);
  const mobileSearchRef = useRef<HTMLInputElement>(null);
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
  useEffect(() => { setMoreOpen(false); setSearchOpen(false); }, [pathname]);
  useEffect(() => { if (searchOpen) mobileSearchRef.current?.focus(); }, [searchOpen]);
  const search = (e: FormEvent) => { e.preventDefault(); setSearchOpen(false); nav(`/leads?q=${encodeURIComponent(q)}`); };

  const items = [
    { to: "/", end: true, label: "Home", icon: LayoutDashboard },
    { to: "/leads", label: "Leads", icon: Inbox, badge: chips.needs_review },
    { to: "/conversations", label: "Chats", icon: MessageSquare, badge: chips.unread },
    { to: "/followups", label: "Tasks", icon: CalendarClock, badge: chips.followup_due },
  ];
  const setup = manager ? [
    { to: "/properties", label: "Properties", icon: Building2, hint: "Projects and price ranges" },
    { to: "/forms", label: "Flows", icon: Workflow, hint: "Lead forms and WhatsApp questions" },
    { to: "/imports", label: "Sheet", icon: Download, hint: "Every sheet row: messaged or not, and why" },
    { to: "/settings", label: "Settings", icon: Settings, hint: "WhatsApp, sheet and team" },
  ] : [];
  const t = title(pathname);
  const initials = (user?.full_name || "?").split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2);
  const fullBleed = pathname.startsWith("/conversations");
  // On a phone an open chat takes the whole screen (it has its own header with a back button).
  const chatOpen = /^\/conversations\/[^/]+/.test(pathname);
  const onSetupPage = setup.some((s) => pathname.startsWith(s.to));

  return (
    <div className="h-app flex overflow-hidden bg-canvas">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2">Skip to content</a>

      {/* Desktop / tablet: icon rail */}
      <aside className="hidden h-full w-[80px] shrink-0 flex-col items-center bg-forest px-2 py-3 md:flex" aria-label="Main navigation">
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
        {/* Desktop header */}
        <header className="z-20 hidden h-14 shrink-0 items-center gap-4 border-b border-line bg-white px-6 md:flex">
          <div className="min-w-0 flex-1">
            {t.parent ? (
              <Link to={t.parent.to} className="inline-flex items-center gap-1 text-sm font-medium text-ink-3 transition-colors hover:text-ink">← Back to {t.parent.label}</Link>
            ) : (
              <div className="flex items-center gap-2.5">
                <Wordmark className="text-[17px]" />
                <span className="hidden h-4 w-px bg-line-strong lg:block" aria-hidden />
                <span className="hidden text-[13px] text-ink-3 lg:inline">{BRAND.tagline}</span>
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

        {/* Phone header */}
        <header className={clsx("z-20 shrink-0 border-b border-line bg-white md:hidden", chatOpen && "hidden")}>
          <div className="flex h-14 items-center gap-2 px-3">
            {t.parent ? (
              <Link to={t.parent.to} aria-label={`Back to ${t.parent.label}`} className="-ml-1 flex h-10 w-10 items-center justify-center rounded-full text-ink-2 active:bg-slate-100"><ArrowLeft className="h-5 w-5" /></Link>
            ) : (
              <Link to="/" aria-label={`${BRAND.name} home`}><LogoMark /></Link>
            )}
            <h1 className="min-w-0 flex-1 truncate text-[17px] font-semibold text-ink">{t.parent ? t.label : t.label === "Dashboard" ? <Wordmark className="text-[17px]" /> : t.label}</h1>
            <button onClick={() => setSearchOpen((v) => !v)} aria-label="Search leads" aria-expanded={searchOpen}
              className={clsx("flex h-10 w-10 items-center justify-center rounded-full text-ink-2 active:bg-slate-100", searchOpen && "bg-slate-100")}>
              {searchOpen ? <X className="h-5 w-5" /> : <Search className="h-5 w-5" />}
            </button>
            <button onClick={() => nav("/leads?add=1")} aria-label="Add lead" className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-700 text-white shadow-xs active:bg-brand-800">
              <Plus className="h-5 w-5" />
            </button>
          </div>
          {searchOpen && (
            <form onSubmit={search} role="search" className="relative px-3 pb-3">
              <Search className="pointer-events-none absolute left-6 top-3 h-4 w-4 text-ink-4" aria-hidden />
              <input ref={mobileSearchRef} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search leads" enterKeyHint="search"
                placeholder="Name, phone or lead ID" className="input h-10 bg-canvas pl-9" />
            </form>
          )}
        </header>

        <main id="main" className={clsx("scroll-thin min-h-0 flex-1", fullBleed ? "overflow-hidden" : "overflow-auto")}><Outlet /></main>

        {/* Phone bottom tabs */}
        <nav aria-label="Main navigation" className={clsx("z-20 flex shrink-0 border-t border-line bg-white pb-[env(safe-area-inset-bottom)] md:hidden", chatOpen && "hidden")}>
          {items.map((i) => <TabItem key={i.to} {...i} />)}
          <button onClick={() => setMoreOpen(true)} aria-haspopup="dialog"
            className={clsx("flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[11px] font-medium", onSetupPage ? "text-brand-700" : "text-ink-3")}>
            <span className={clsx("flex h-7 w-12 items-center justify-center rounded-full", onSetupPage && "bg-brand-50")}><Menu size={20} strokeWidth={1.8} aria-hidden /></span>
            More
          </button>
        </nav>
      </div>

      {/* Phone "More" sheet */}
      {moreOpen && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end bg-slate-900/40 md:hidden" onClick={() => setMoreOpen(false)}>
          <div role="dialog" aria-modal="true" aria-label="More" className="animate-fade-up rounded-t-2xl bg-white pb-[env(safe-area-inset-bottom)] shadow-pop" onClick={(e) => e.stopPropagation()}>
            <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-slate-200" aria-hidden />
            <div className="flex items-center gap-3 border-b border-line px-5 py-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-sm font-semibold text-brand-800">{initials}</div>
              <div className="min-w-0 flex-1"><div className="truncate font-semibold text-ink">{user?.full_name}</div><div className="text-xs capitalize text-ink-3">{user?.role}</div></div>
              <button onClick={() => setMoreOpen(false)} aria-label="Close" className="flex h-10 w-10 items-center justify-center rounded-full text-ink-3 active:bg-slate-100"><X className="h-5 w-5" /></button>
            </div>
            {manager && (
              <div className="flex gap-2 overflow-x-auto px-5 pt-3">
                <StatusDot ok={wa ? wa.configured && !!wa.last_webhook_at : null} label={wa?.configured ? "WhatsApp connected" : "WhatsApp setup"} />
                <StatusDot ok={sync ? sync.ok : null} label={`Sheet sync${sync ? " · " + timeAgo(sync.at) : ""}`} />
              </div>
            )}
            <nav className="px-2 py-2" aria-label="Setup">
              {setup.map(({ to, label, icon: Icon, hint }) => (
                <Link key={to} to={to} className="flex items-center gap-3 rounded-xl px-3 py-3 active:bg-slate-50">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-ink-2"><Icon className="h-5 w-5" /></span>
                  <span className="min-w-0 flex-1"><span className="block font-medium text-ink">{label}</span><span className="block truncate text-xs text-ink-3">{hint}</span></span>
                  <ChevronRight className="h-4 w-4 text-ink-4" />
                </Link>
              ))}
              <button onClick={logout} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-red-600 active:bg-red-50">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-50"><LogOut className="h-5 w-5" /></span>
                <span className="font-medium">Sign out</span>
              </button>
            </nav>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusDot({ ok, label }: { ok: boolean | null; label: string }) {
  return (
    <span className={clsx("inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
      ok ? "border-brand-200 bg-brand-50 text-brand-800" : ok === false ? "border-amber-200 bg-amber-50 text-amber-800" : "border-line text-ink-3")}>
      <span className={clsx("h-1.5 w-1.5 rounded-full", ok ? "bg-brand-500" : ok === false ? "bg-amber-500" : "bg-ink-4")} aria-hidden />{label}
    </span>
  );
}
