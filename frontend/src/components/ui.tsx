import clsx from "clsx";
import { AlertCircle, Inbox, Loader2, X } from "lucide-react";
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { STATUS_LABEL } from "../lib/format";

// ------------------------------------------------------------------ buttons

type BtnVariant = "primary" | "secondary" | "danger" | "ghost" | "violet" | "subtle";
export function Button({ variant = "primary", size = "md", loading, className, children, ...rest }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md"; loading?: boolean }) {
  return (
    <button
      type={rest.type || "button"}
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        "inline-flex shrink-0 select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-semibold transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50",
        size === "sm" ? "h-9 px-3 text-xs sm:h-8 sm:px-2.5" : "h-10 px-3.5 text-sm sm:h-9",
        variant === "primary" && "bg-brand-700 text-white shadow-xs hover:bg-brand-800",
        variant === "violet" && "bg-violet-600 text-white shadow-xs hover:bg-violet-700",
        variant === "secondary" && "border border-line-strong bg-white text-ink-2 shadow-xs hover:bg-slate-50 hover:text-ink",
        variant === "subtle" && "bg-brand-50 text-brand-800 hover:bg-brand-100",
        variant === "danger" && "bg-red-600 text-white shadow-xs hover:bg-red-700",
        variant === "ghost" && "text-ink-3 hover:bg-slate-100 hover:text-ink",
        className,
      )}
    >
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function IconButton({ label, className, children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button type="button" aria-label={label} title={label} {...rest}
      className={clsx("inline-flex h-10 w-10 items-center justify-center rounded-lg text-ink-3 sm:h-8 sm:w-8 transition-colors hover:bg-slate-100 hover:text-ink disabled:opacity-40", className)}>
      {children}
    </button>
  );
}

// ------------------------------------------------------------------ surfaces

export function Card({ title, subtitle, action, children, className, bodyClass, icon }:
  { title?: ReactNode; subtitle?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; icon?: ReactNode }) {
  return (
    <section className={clsx("card min-w-0", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            {icon && <span className="text-ink-3">{icon}</span>}
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold text-ink">{title}</h2>
              {subtitle && <p className="truncate text-xs text-ink-3">{subtitle}</p>}
            </div>
          </div>
          {action}
        </header>
      )}
      <div className={clsx("p-4", bodyClass)}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3 sm:mb-5">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium text-ink-3">{eyebrow}</div>}
        <h1 className="text-xl font-semibold leading-tight tracking-tight text-ink sm:text-[22px]">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-ink-3">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** KPI card: label, figure, one line of context. The small icon only changes tone to flag
 *  something that needs attention. */
export function StatCard({ label, value, hint, icon, tone = "brand", onClick }:
  { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: "brand" | "red" | "amber" | "blue" | "violet" | "slate"; onClick?: () => void }) {
  const tones = { brand: "bg-brand-50 text-brand-700", red: "bg-red-50 text-red-600", amber: "bg-amber-50 text-amber-700",
    blue: "bg-sky-50 text-sky-700", violet: "bg-violet-50 text-violet-700", slate: "bg-slate-100 text-ink-3" };
  const Tag: any = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick} className={clsx("flex w-full min-w-0 flex-col rounded-xl border border-line bg-white p-3.5 text-left shadow-xs transition-colors sm:p-4", onClick && "hover:border-line-strong hover:bg-slate-50/50")}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[13px] font-medium text-ink-3">{label}</p>
        {icon && <span className={clsx("flex h-7 w-7 items-center justify-center rounded-md", tones[tone])}>{icon}</span>}
      </div>
      <p className="kpi mt-2 text-[26px] font-semibold leading-none tracking-tight text-ink">{value}</p>
      {hint && <p className="mt-2 text-xs text-ink-3">{hint}</p>}
    </Tag>
  );
}

/** Small uppercase section label with a green dot (e.g. "● WHATSAPP"). */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx("inline-flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-brand-700", className)}>
      <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-pulse-dot rounded-full bg-brand-400" /><span className="relative inline-flex h-2 w-2 rounded-full bg-brand-500" /></span>
      {children}
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items, className, size = "md" }:
  { value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode; count?: number }[]; className?: string; size?: "sm" | "md" }) {
  return (
    <div role="tablist" className={clsx("no-scrollbar inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-xl bg-slate-100 p-1", className)}>
      {items.map((i) => (
        <button key={i.value} role="tab" aria-selected={value === i.value} data-active={value === i.value} onClick={() => onChange(i.value)}
          className={clsx("chip-tab", size === "sm" && "h-7 flex-1 justify-center px-2")}>
          {i.label}
          {i.count !== undefined && <span className={clsx("rounded-md px-1.5 text-2xs font-semibold tabular", value === i.value ? "bg-slate-100 text-ink-2" : "text-ink-4")}>{i.count}</span>}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ badges

const STATUS_STYLE: Record<string, [string, string]> = {
  new: ["bg-blue-50 text-blue-700", "bg-blue-500"],
  contacted: ["bg-slate-100 text-slate-700", "bg-slate-400"],
  qualified: ["bg-emerald-50 text-emerald-700", "bg-emerald-500"],
  site_visit: ["bg-violet-50 text-violet-700", "bg-violet-500"],
  negotiation: ["bg-amber-50 text-amber-800", "bg-amber-500"],
  won: ["bg-green-100 text-green-800", "bg-green-600"],
  lost: ["bg-red-50 text-red-700", "bg-red-500"],
  nurture: ["bg-orange-50 text-orange-800", "bg-orange-400"],
};

export function Chip({ className, children, dot }: { className?: string; children: ReactNode; dot?: string }) {
  return (
    <span className={clsx("inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-medium", className)}>
      {dot && <span className={clsx("h-1.5 w-1.5 rounded-full", dot)} aria-hidden />}
      {children}
    </span>
  );
}

export function StatusChip({ status }: { status: string }) {
  const [cls, dot] = STATUS_STYLE[status] || STATUS_STYLE.contacted;
  return <Chip className={cls} dot={dot}>{STATUS_LABEL[status] || status}</Chip>;
}

export function PriorityChip({ priority }: { priority?: string | null }) {
  if (!priority) return <span className="text-ink-4">—</span>;
  const map: Record<string, [string, string]> = {
    hot: ["bg-red-50 text-red-700 ring-1 ring-inset ring-red-200", "bg-red-500"],
    warm: ["bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200", "bg-amber-500"],
    cold: ["bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200", "bg-blue-500"],
  };
  const [cls, dot] = map[priority];
  return <Chip className={cls} dot={dot}>{priority[0].toUpperCase() + priority.slice(1)}</Chip>;
}

export function ModeChip({ mode }: { mode: string }) {
  const map: Record<string, [string, string, string]> = {
    bot: ["Bot", "bg-brand-50 text-brand-800", "bg-brand-500"],
    human: ["Human", "bg-violet-50 text-violet-700", "bg-violet-500"],
    handoff: ["Needs person", "bg-amber-50 text-amber-800", "bg-amber-500"],
    done: ["Completed", "bg-emerald-50 text-emerald-700", "bg-emerald-500"],
    blocked: ["No consent", "bg-slate-100 text-slate-600", "bg-slate-400"],
    opted_out: ["Opted out", "bg-red-50 text-red-700", "bg-red-500"],
    none: ["—", "bg-transparent text-ink-4", ""],
  };
  const [label, cls, dot] = map[mode] || map.none;
  return <Chip className={cls} dot={dot || undefined}>{label}</Chip>;
}

export function ConsentChip({ status }: { status: string }) {
  const map: Record<string, [string, string, string]> = {
    opted_in: ["Opted in", "bg-emerald-50 text-emerald-700", "bg-emerald-500"],
    unknown: ["No consent", "bg-amber-50 text-amber-800", "bg-amber-500"],
    opted_out: ["Opted out", "bg-red-50 text-red-700", "bg-red-500"],
  };
  const [label, cls, dot] = map[status] || map.unknown;
  return <Chip className={cls} dot={dot}>{label}</Chip>;
}

// ------------------------------------------------------------------ avatar

const AVATAR = ["bg-teal-100 text-teal-800", "bg-sky-100 text-sky-800", "bg-violet-100 text-violet-800", "bg-amber-100 text-amber-800",
  "bg-rose-100 text-rose-800", "bg-emerald-100 text-emerald-800", "bg-indigo-100 text-indigo-800"];

export function Avatar({ name, size = "md", className }: { name?: string | null; size?: "xs" | "sm" | "md" | "lg"; className?: string }) {
  const n = (name || "?").trim();
  const initials = n.split(/\s+/).filter((p) => /[A-Za-z0-9]/.test(p[0])).map((p) => p[0]).slice(0, 2).join("").toUpperCase() || "?";
  const color = AVATAR[[...n].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR.length];
  const sz = { xs: "h-6 w-6 text-[10px]", sm: "h-8 w-8 text-xs", md: "h-9 w-9 text-xs", lg: "h-12 w-12 text-base" }[size];
  return <span aria-hidden className={clsx("inline-flex shrink-0 items-center justify-center rounded-full font-semibold", sz, color, className)}>{initials}</span>;
}

// ------------------------------------------------------------------ states

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("h-5 w-5 animate-spin text-brand-700", className)} aria-label="Loading" />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} />;
}

export function Loading({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-8 w-8 rounded-full" />
          <div className="flex-1 space-y-1.5"><Skeleton className="h-3 w-1/3" /><Skeleton className="h-3 w-1/2" /></div>
        </div>
      ))}
    </div>
  );
}

export function Empty({ title, hint, action, icon }: { title: string; hint?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="mb-1 flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-ink-3">{icon || <Inbox className="h-5 w-5" />}</div>
      <div className="text-sm font-semibold text-ink">{title}</div>
      {hint && <div className="max-w-sm text-sm text-ink-3">{hint}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorBox({ error }: { error: any }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>{error.message || String(error)}{error.correlationId && <span className="ml-2 text-xs text-red-400">ref {error.correlationId}</span>}</div>
    </div>
  );
}

// ------------------------------------------------------------------ overlays & forms

export function Modal({ open, title, onClose, children, width = "max-w-lg", description }:
  { open: boolean; title: string; onClose: () => void; children: ReactNode; width?: string; description?: string }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    // Phone: a bottom sheet that can scroll; larger screens: a centred dialog.
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 backdrop-blur-[2px] sm:items-start sm:overflow-y-auto sm:p-4 sm:pt-[10vh]" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className={clsx("flex max-h-[92dvh] w-full animate-fade-up flex-col rounded-t-2xl bg-white shadow-pop sm:max-h-none sm:rounded-2xl", width)}
        onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex shrink-0 items-start justify-between gap-4 px-5 pb-2 pt-4 sm:px-6 sm:pt-5">
          <div><h2 className="text-base font-semibold text-ink">{title}</h2>{description && <p className="mt-0.5 text-sm text-ink-3">{description}</p>}</div>
          <IconButton label="Close" onClick={onClose}><X className="h-4 w-4" /></IconButton>
        </div>
        <div className="overflow-y-auto px-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] pt-3 sm:px-6 sm:pb-6">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, error, children, hint }: { label: string; error?: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-ink-3">{hint}</span>}
      {error && <span role="alert" className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, disabled, label }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onChange(!checked)}
      className={clsx("relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors duration-150 disabled:opacity-50", checked ? "bg-brand-700" : "bg-slate-300")}>
      <span className={clsx("absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-150", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
    </button>
  );
}

// ------------------------------------------------------------------ toasts

type Toast = { id: number; text: string; kind: "ok" | "error" };
const ToastCtx = createContext<(text: string, kind?: "ok" | "error") => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, kind: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-20 z-[60] flex flex-col items-center gap-2 sm:inset-x-auto sm:bottom-5 sm:right-5 sm:items-end">
        {toasts.map((t) => (
          <div key={t.id} className={clsx("pointer-events-auto flex w-full max-w-sm animate-fade-up items-start gap-2 rounded-xl px-4 py-3 text-sm font-medium text-white shadow-pop", t.kind === "ok" ? "bg-ink" : "bg-red-600")}>
            {t.kind === "error" && <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}{t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
