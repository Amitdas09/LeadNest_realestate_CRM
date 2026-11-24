import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, ArrowLeft, Bot, Check, CheckCheck, Clock, ExternalLink, FileText, Info, Lock, MessageSquare, Search, SendHorizontal, StickyNote, UserRound, XCircle } from "lucide-react";
import { FormEvent, Fragment, KeyboardEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Avatar, Button, ConsentChip, Empty, ErrorBox, Loading, ModeChip, PriorityChip, StatusChip, Tabs, useToast } from "../components/ui";
import { api } from "../lib/api";
import { clock, dayLabel, timeAgo } from "../lib/format";

type Filter = "all" | "mine" | "unread" | "handoff" | "human";

export default function Conversations() {
  const { convId } = useParams();
  const nav = useNavigate();
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const list = useQuery({
    queryKey: ["conversations", filter, q],
    queryFn: () => api("/api/v1/conversations", { query: { filter, q } }),
    refetchInterval: 4000,
  });

  useEffect(() => {
    // Wide screens open the newest chat next to the list; phones show the list first.
    if (!convId && list.data?.items?.length && window.matchMedia("(min-width: 768px)").matches)
      nav(`/conversations/${list.data.items[0].conversation_id}`, { replace: true });
  }, [convId, list.data, nav]);

  return (
    <div className="flex h-full min-h-0">
      <aside className={clsx("w-full shrink-0 flex-col border-r border-line bg-white md:flex md:w-[300px]", convId ? "hidden" : "flex")} aria-label="Conversations">
        <div className="space-y-3 border-b border-line p-3">
          <div className="flex items-center justify-between"><h1 className="text-base font-semibold text-ink">Conversations</h1>
            <span className="text-xs text-ink-3">{list.data?.items?.length ?? "…"}</span></div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-3 h-4 w-4 text-ink-4 sm:top-2" aria-hidden />
            <input aria-label="Search conversations" className="input pl-8 sm:h-8 sm:text-xs" placeholder="Search by name" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Tabs value={filter} onChange={setFilter} className="flex w-full" size="sm"
            items={[{ value: "all", label: "All" }, { value: "mine", label: "Mine" }, { value: "unread", label: "Unread" }, { value: "handoff", label: "Waiting" }, { value: "human", label: "Human" }]} />
        </div>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {list.isLoading ? <Loading rows={6} /> : list.data.items.length === 0 ? (
            <Empty title="No conversations" hint="A conversation appears once the first WhatsApp message is sent or received." icon={<MessageSquare className="h-5 w-5" />} />
          ) : list.data.items.map((c: any) => {
            const active = c.conversation_id === convId;
            return (
              <Link key={c.id} to={`/conversations/${c.conversation_id}`} aria-current={active ? "page" : undefined}
                className={clsx("flex gap-3 border-b border-line/60 px-3 py-3 transition-colors", active ? "bg-brand-50/70" : "hover:bg-slate-50")}>
                <div className="relative">
                  <Avatar name={c.full_name} />
                  {c.unread_count > 0 && <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-700 px-1 text-[10px] font-bold text-white">{c.unread_count}</span>}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className={clsx("truncate text-sm", c.unread_count ? "font-bold text-ink" : "font-semibold text-ink")}>{c.full_name}</span>
                    <span className="shrink-0 text-2xs text-ink-4">{timeAgo(c.last_message_at)}</span>
                  </div>
                  <div className={clsx("mt-0.5 truncate text-xs", c.unread_count ? "text-ink-2" : "text-ink-3")}>{c.last_message_preview || "—"}</div>
                  <div className="mt-1.5 flex gap-1"><ModeChip mode={c.mode} />{c.priority && <PriorityChip priority={c.priority} />}</div>
                </div>
              </Link>
            );
          })}
        </div>
      </aside>
      {convId ? <Thread key={convId} convId={convId} /> : (
        <div className="hidden flex-1 items-center justify-center bg-canvas md:flex"><Empty title="Select a conversation" icon={<MessageSquare className="h-5 w-5" />} /></div>
      )}
    </div>
  );
}

function Ticks({ m }: { m: any }) {
  if (m.direction !== "out") return null;
  if (m.status === "queued") return <Clock className="h-3 w-3 text-ink-4" aria-label="Queued" />;
  if (m.status === "failed" || m.status === "blocked") return <XCircle className="h-3 w-3 text-red-500" aria-label="Not delivered" />;
  if (m.status === "read") return <CheckCheck className="h-3.5 w-3.5 text-sky-500" aria-label="Read" />;
  if (m.status === "delivered") return <CheckCheck className="h-3.5 w-3.5 text-ink-4" aria-label="Delivered" />;
  return <Check className="h-3 w-3 text-ink-4" aria-label="Sent" />;
}

function Bubble({ m }: { m: any }) {
  const out = m.direction === "out";
  const failed = m.status === "failed" || m.status === "blocked";
  const label = m.sender_type === "template" ? "Template" : m.sender_type === "bot" ? "Assistant" : m.sender_type === "agent" ? (m.kind === "template" ? `${m.sender?.name || "Agent"} · template` : m.sender?.name || "Agent") : null;
  return (
    <div className={clsx("flex animate-fade-up", out ? "justify-end" : "justify-start")}>
      <div className={clsx("max-w-[86%] rounded-2xl px-3.5 py-2 shadow-xs sm:max-w-[min(72%,560px)]",
        !out && "rounded-bl-md bg-white", out && m.sender_type === "agent" && "rounded-br-md bg-violet-100", out && m.sender_type !== "agent" && "rounded-br-md bg-wa-bubble",
        failed && "ring-1 ring-red-300")}>
        {label && <div className={clsx("mb-0.5 flex items-center gap-1 text-2xs font-semibold", m.sender_type === "agent" ? "text-violet-700" : "text-brand-800")}>
          {m.sender_type === "agent" ? <UserRound className="h-3 w-3" /> : <Bot className="h-3 w-3" />}{label}</div>}
        <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-ink">{m.body}</div>
        {m.options?.length > 0 && (
          <div className="mt-2 grid gap-1">
            {m.options.map((o: string) => <span key={o} className="rounded-lg bg-white/80 px-2 py-1 text-center text-xs font-semibold text-wa-green ring-1 ring-black/5">{o}</span>)}
          </div>
        )}
        {failed && <div className="mt-1 flex items-start gap-1 text-xs font-medium text-red-600"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{m.status === "blocked" ? "Not sent" : "Failed"}: {m.error_message || m.error_code}</div>}
        <div className="mt-0.5 flex items-center justify-end gap-1 text-2xs text-ink-3">{clock(m.created_at)} <Ticks m={m} /></div>
      </div>
    </div>
  );
}

// Phones: Enter adds a new line and the Send button sends (like WhatsApp); keyboards: Enter sends.
const touchDevice = () => window.matchMedia("(pointer: coarse)").matches;

function Thread({ convId }: { convId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const [text, setText] = useState("");
  const [noteMode, setNoteMode] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false); // phones / tablets: details as a full-screen sheet
  const bottom = useRef<HTMLDivElement>(null);
  const q = useQuery({ queryKey: ["thread", convId], queryFn: () => api(`/api/v1/conversations/${convId}/messages`), refetchInterval: 2500 });
  const lead = useQuery({ queryKey: ["lead", q.data?.lead?.id], queryFn: () => api(`/api/v1/leads/${q.data.lead.id}`), enabled: !!q.data?.lead?.id, refetchInterval: 5000 });
  // Outside the 24h window, typed messages can still go out if the "agent_message" template is approved.
  const windowClosedHuman = !!q.data && q.data.conversation.mode === "human" && !q.data.conversation.window_open;
  const templates = useQuery({ queryKey: ["wa-templates"], queryFn: () => api("/api/v1/conversations/meta/templates"), staleTime: 60000, enabled: windowClosedHuman });
  const agentTplReady = (templates.data?.items || []).some((t: any) => t.name === "agent_message" && t.params >= 2);
  const count = (q.data?.messages?.length || 0) + (lead.data?.notes?.length || 0);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [count]);

  const refresh = () => { ["thread", "conversations", "lead", "nav-counts"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); };
  const onErr = (e: any) => { toast(e.message, "error"); refresh(); };
  const takeover = useMutation({ mutationFn: () => api(`/api/v1/conversations/${convId}/takeover`, { body: { version: q.data.conversation.version } }), onSuccess: () => { refresh(); toast("You're handling this chat now. The assistant is paused."); }, onError: onErr });
  const resume = useMutation({ mutationFn: () => api(`/api/v1/conversations/${convId}/resume-bot`, { body: { version: q.data.conversation.version } }), onSuccess: () => { refresh(); toast("Back to the assistant. It continues from the next unanswered question."); }, onError: onErr });
  const send = useMutation({
    mutationFn: () => noteMode
      ? api(`/api/v1/leads/${q.data.lead.id}/notes`, { body: { body: text.trim() } })
      : api(`/api/v1/conversations/${convId}/messages`, { body: { text: text.trim(), idempotency_key: crypto.randomUUID() } }),
    onSuccess: () => { setText(""); refresh(); if (noteMode) toast("Internal note saved (never sent to the customer)"); },
    onError: onErr,
  });

  if (q.isLoading) return <div className="flex-1 bg-canvas"><Loading /></div>;
  if (q.error) return <div className="flex-1 p-6"><ErrorBox error={q.error} /></div>;
  const { conversation: c, lead: l, messages } = q.data;
  const human = c.mode === "human";
  const optedOut = l.consent_status === "opted_out";
  const notes = (lead.data?.notes || []).map((n: any) => ({ ...n, _note: true }));
  const items = [...messages, ...notes].sort((a: any, b: any) => a.created_at.localeCompare(b.created_at));
  const windowLeft = c.window_expires_at ? Math.max(0, new Date(c.window_expires_at).getTime() - Date.now()) : 0;
  const submit = (e?: FormEvent) => { e?.preventDefault(); if (text.trim() && !send.isPending) send.mutate(); };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === "Enter" && !e.shiftKey && !touchDevice()) { e.preventDefault(); submit(); } };

  return (
    <>
      <div className="flex min-w-0 flex-1 flex-col bg-canvas">
        <header className="flex items-center justify-between gap-2 border-b border-line bg-white px-2 py-2 sm:gap-3 sm:px-5 sm:py-3">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <button onClick={() => nav("/conversations")} aria-label="Back to chats" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-ink-2 active:bg-slate-100 md:hidden">
              <ArrowLeft className="h-5 w-5" />
            </button>
            <button onClick={() => setProfileOpen(true)} className="flex min-w-0 items-center gap-2 text-left sm:gap-3 lg:pointer-events-none" aria-label="Show lead details">
              <Avatar name={l.full_name} />
              <div className="min-w-0">
                <div className="flex items-center gap-2"><h2 className="truncate text-sm font-semibold text-ink">{l.full_name}</h2>{l.priority && <span className="hidden sm:inline"><PriorityChip priority={l.priority} /></span>}</div>
                <div className="truncate text-xs text-ink-3">{l.property?.name || "No property"} · {l.phone_masked}</div>
              </div>
            </button>
          </div>
          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            {human ? (
              <>
                <span className="hidden items-center gap-1.5 rounded-lg bg-violet-50 px-2.5 py-1.5 text-xs font-semibold text-violet-700 xl:flex"><UserRound className="h-3.5 w-3.5" /> {c.assigned_agent?.name || "Agent"} is replying</span>
                <Button size="sm" variant="secondary" onClick={() => resume.mutate()} loading={resume.isPending} title="Return to assistant">
                  <Bot className="h-3.5 w-3.5" /><span className="sm:hidden">Bot</span><span className="hidden sm:inline">Return to assistant</span>
                </Button>
              </>
            ) : (
              <>
                <span className="hidden items-center gap-1.5 rounded-lg bg-brand-50 px-2.5 py-1.5 text-xs font-semibold text-brand-800 xl:flex">
                  <Bot className="h-3.5 w-3.5" /> {c.state === "handoff" ? "Waiting for a person" : c.state === "completed" ? "Assistant finished" : "Assistant is replying"}
                </span>
                <Button size="sm" variant="violet" onClick={() => takeover.mutate()} loading={takeover.isPending} disabled={optedOut}><UserRound className="h-3.5 w-3.5" /> Take over</Button>
              </>
            )}
            <button onClick={() => setProfileOpen(true)} aria-label="Lead details" className="flex h-10 w-10 items-center justify-center rounded-full text-ink-2 active:bg-slate-100 lg:hidden">
              <Info className="h-5 w-5" />
            </button>
          </div>
        </header>
        {/* Phones: who is replying, under the header (desktop shows it next to the buttons). */}
        <div className={clsx("flex items-center gap-1.5 border-b border-line px-4 py-1.5 text-xs font-medium xl:hidden", human ? "bg-violet-50 text-violet-700" : "bg-brand-50/70 text-brand-800")}>
          {human ? <><UserRound className="h-3.5 w-3.5" /> {c.assigned_agent?.name || "Agent"} is replying · assistant paused</>
            : <><Bot className="h-3.5 w-3.5" /> {c.state === "handoff" ? "Waiting for a person" : c.state === "completed" ? "Assistant finished" : "Assistant is replying"}</>}
          {l.priority && <span className="ml-auto sm:hidden"><PriorityChip priority={l.priority} /></span>}
        </div>

        <div className="chat-bg scroll-thin min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5" aria-live="polite">
          {items.length === 0 && <Empty title="No messages yet" />}
          {items.map((m: any, i: number) => {
            const prev = items[i - 1];
            const showDay = !prev || dayLabel(prev.created_at) !== dayLabel(m.created_at);
            return (
              <Fragment key={(m._note ? "n" : "m") + m.id}>
                {showDay && <div className="my-3 text-center"><span className="rounded-lg bg-white/90 px-2.5 py-1 text-2xs font-medium text-ink-3 shadow-xs">{dayLabel(m.created_at)}</span></div>}
                {m._note ? (
                  <div className="mx-auto flex max-w-[92%] items-start gap-2 sm:max-w-[78%] rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-sm text-amber-900">
                    <StickyNote className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                    <div><span className="font-semibold">{m.author?.name}</span> <span className="text-xs text-amber-700">· internal note · {clock(m.created_at)}</span><div className="whitespace-pre-wrap">{m.body}</div></div>
                  </div>
                ) : <Bubble m={m} />}
              </Fragment>
            );
          })}
          <div ref={bottom} />
        </div>

        <div className="border-t border-line bg-white px-3 pb-[calc(0.5rem+env(safe-area-inset-bottom))] pt-2 sm:px-5 sm:py-3">
          {optedOut && !noteMode ? (
            <Notice icon={<Lock className="h-4 w-4" />} tone="red" title="This customer opted out" text="They replied STOP, so WhatsApp messages can't be sent. You can still add internal notes." action={<Button size="sm" variant="secondary" onClick={() => setNoteMode(true)}><StickyNote className="h-3.5 w-3.5" /> Add note</Button>} />
          ) : !human && !noteMode ? (
            <Notice icon={<Bot className="h-4 w-4" />} tone="brand" title="The assistant is handling this chat"
              text="Take over to reply yourself. The assistant pauses immediately and nothing it had queued is sent."
              action={<div className="flex gap-2"><Button size="sm" variant="secondary" onClick={() => setNoteMode(true)}><StickyNote className="h-3.5 w-3.5" /> Note</Button>
                <Button size="sm" variant="violet" onClick={() => takeover.mutate()} loading={takeover.isPending}><UserRound className="h-3.5 w-3.5" /> Take over</Button></div>} />
          ) : human && !c.window_open && !noteMode && !agentTplReady ? (
            <TemplateComposer convId={convId} lead={l} onSent={refresh} onNote={() => setNoteMode(true)} />
          ) : (
            <form onSubmit={submit}>
              <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                {noteMode
                  ? <span className="flex items-center gap-1.5 font-medium text-amber-700"><StickyNote className="h-3.5 w-3.5" /> Internal note · only your team can see this</span>
                  : c.window_open
                    ? <span className="flex items-center gap-1.5 text-emerald-700"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />Reply window open · {Math.floor(windowLeft / 3600000)}h {Math.floor((windowLeft % 3600000) / 60000)}m left</span>
                    : <span className="flex items-center gap-1.5 text-amber-700"><span className="h-1.5 w-1.5 rounded-full bg-amber-500" />No reply in 24h · your message is delivered through the approved “agent_message” template</span>}
                <span className="hidden shrink-0 text-ink-4 lg:inline">Enter to send · Shift+Enter for a new line</span>
              </div>
              <div className={clsx("flex items-end gap-2 rounded-xl border p-1.5 transition-colors focus-within:ring-2", noteMode ? "border-amber-300 bg-amber-50/50 focus-within:ring-amber-300/40" : "border-line-strong focus-within:border-brand-600 focus-within:ring-brand-600/20")}>
                <textarea aria-label={noteMode ? "Internal note" : "Message"} rows={1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} autoFocus={!touchDevice()}
                  placeholder={noteMode ? "Write an internal note…" : "Type a WhatsApp message…"} enterKeyHint={touchDevice() ? "enter" : "send"}
                  className="max-h-40 min-h-[40px] min-w-0 flex-1 resize-none bg-transparent px-2 py-2 text-base outline-none placeholder:text-ink-4 sm:min-h-[36px] sm:py-1.5 sm:text-sm" />
                <Button type="button" size="sm" variant={noteMode ? "subtle" : "ghost"} onClick={() => setNoteMode(!noteMode)} aria-pressed={noteMode} title="Toggle internal note">
                  <StickyNote className="h-4 w-4" />{noteMode ? "Note" : ""}
                </Button>
                <Button type="submit" size="sm" variant={noteMode ? "secondary" : "primary"} disabled={!text.trim()} loading={send.isPending}>
                  {noteMode ? "Save note" : <><SendHorizontal className="h-4 w-4" /> Send</>}
                </Button>
              </div>
              {noteMode && (!human || !c.window_open) && <button type="button" onClick={() => setNoteMode(false)} className="mt-1.5 text-xs font-medium text-ink-3 hover:text-ink">Cancel note</button>}
            </form>
          )}
        </div>
      </div>
      {/* Desktop: side panel. Phones / tablets: full-screen sheet from the header. */}
      <div className="hidden lg:flex"><Profile lead={lead.data} conv={c} /></div>
      {profileOpen && (
        <div className="fixed inset-0 z-50 flex flex-col bg-white lg:hidden" role="dialog" aria-modal="true" aria-label="Lead details">
          <div className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-2">
            <button onClick={() => setProfileOpen(false)} aria-label="Back to chat" className="flex h-10 w-10 items-center justify-center rounded-full text-ink-2 active:bg-slate-100"><ArrowLeft className="h-5 w-5" /></button>
            <span className="font-semibold text-ink">Lead details</span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto pb-[env(safe-area-inset-bottom)]"><Profile lead={lead.data} conv={c} sheet /></div>
        </div>
      )}
    </>
  );
}

function Notice({ icon, title, text, action, tone }: { icon: React.ReactNode; title: string; text: string; action?: React.ReactNode; tone: "brand" | "red" | "amber" }) {
  return (
    <div className={clsx("flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3",
      tone === "brand" && "border-brand-100 bg-brand-50/60", tone === "red" && "border-red-200 bg-red-50", tone === "amber" && "border-amber-200 bg-amber-50")}>
      <span className={clsx("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white shadow-xs", tone === "brand" ? "text-brand-700" : tone === "red" ? "text-red-600" : "text-amber-700")}>{icon}</span>
      <div className="min-w-0 flex-1"><div className="text-sm font-semibold text-ink">{title}</div><div className="text-xs text-ink-3">{text}</div></div>
      {action}
    </div>
  );
}

/** Reply window closed: WhatsApp only allows approved templates until the customer writes again. */
function TemplateComposer({ convId, lead, onSent, onNote }: { convId: string; lead: any; onSent: () => void; onNote: () => void }) {
  const toast = useToast();
  const tpl = useQuery({ queryKey: ["wa-templates"], queryFn: () => api("/api/v1/conversations/meta/templates"), staleTime: 60000 });
  const [sel, setSel] = useState<string>("");
  const items = tpl.data?.items || [];
  useEffect(() => { if (!sel && items.length) setSel(`${items[0].name}|${items[0].language}`); }, [items, sel]);
  const chosen = items.find((t: any) => `${t.name}|${t.language}` === sel);
  const preview = chosen ? chosen.body.replace("{{1}}", (lead.full_name || "").split(" ")[0] || "there").replace("{{2}}", lead.property?.name || "our project") : "";
  const send = useMutation({
    mutationFn: () => api(`/api/v1/conversations/${convId}/template`, { body: { name: chosen.name, language: chosen.language, idempotency_key: crypto.randomUUID() } }),
    onSuccess: () => { toast("Template sent. You can type freely once the customer replies."); onSent(); },
    onError: (e: any) => toast(e.message, "error"),
  });
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-3">
      <div className="flex items-start gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-amber-700 shadow-xs"><Clock className="h-4 w-4" /></span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-ink">Reply window closed — send an approved template</div>
          <div className="text-xs text-ink-3">WhatsApp only allows free text within 24 hours of the customer's last message. Send a template to restart the chat; typing unlocks as soon as they reply.</div>
        </div>
      </div>
      {tpl.isLoading ? <div className="mt-3"><Loading rows={1} /></div> : tpl.error ? <div className="mt-3"><ErrorBox error={tpl.error} /></div> : items.length === 0 ? (
        <div className="mt-3 text-xs text-ink-3">No approved templates yet. Check WhatsApp Manager → Message templates.</div>
      ) : (
        <div className="mt-3 grid gap-3 md:grid-cols-[220px_minmax(0,1fr)_auto] md:items-start">
          <select aria-label="Template" className="input h-9" value={sel} onChange={(e) => setSel(e.target.value)}>
            {items.map((t: any) => <option key={`${t.name}|${t.language}`} value={`${t.name}|${t.language}`}>{t.name} ({t.language})</option>)}
          </select>
          <div className="rounded-lg bg-white px-3 py-2 text-xs text-ink-2 ring-1 ring-line">
            <div className="mb-0.5 flex items-center gap-1 text-2xs font-semibold text-ink-3"><FileText className="h-3 w-3" /> Preview</div>
            <div className="whitespace-pre-wrap">{preview || "—"}</div>
            {chosen?.buttons?.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{chosen.buttons.map((b: string) => <span key={b} className="rounded-md bg-slate-50 px-1.5 py-0.5 text-2xs font-semibold text-wa-green ring-1 ring-line">{b}</span>)}</div>}
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={onNote}><StickyNote className="h-3.5 w-3.5" /> Note</Button>
            <Button size="sm" onClick={() => send.mutate()} loading={send.isPending} disabled={!chosen}><SendHorizontal className="h-3.5 w-3.5" /> Send template</Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Profile({ lead, conv, sheet }: { lead: any; conv: any; sheet?: boolean }) {
  const box = sheet ? "w-full p-4" : "scroll-thin w-[320px] shrink-0 overflow-y-auto border-l border-line p-4";
  if (!lead) return <aside className={clsx(box, "bg-white")}><Loading /></aside>;
  const answered = new Map(lead.requirements.map((r: any) => [r.field_key, r]));
  const done = ["completed", "handoff", "closed", "opted_out"].includes(conv.state);
  const asked = lead.questions.filter((q: any) => answered.has(q.key)).length;
  const pct = lead.questions.length ? Math.round((100 * asked) / lead.questions.length) : 0;
  return (
    <aside className={clsx(box, "space-y-4 bg-white")} aria-label="Lead profile">
      <div className="flex flex-col items-center text-center">
        <Avatar name={lead.full_name} size="lg" />
        <div className="mt-2 font-semibold text-ink">{lead.full_name}</div>
        <div className="text-xs text-ink-3">{lead.phone_masked}</div>
        <div className="mt-2 flex flex-wrap justify-center gap-1"><StatusChip status={lead.status} /><ConsentChip status={lead.consent_status} /></div>
        <Link to={`/leads/${lead.id}`} className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline">Open full profile <ExternalLink className="h-3 w-3" /></Link>
      </div>

      {lead.review_reasons.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <div className="mb-1 flex items-center gap-1 font-semibold"><AlertTriangle className="h-3.5 w-3.5" /> Needs attention</div>
          {lead.review_reasons.map((r: string) => <div key={r}>• {r}</div>)}
        </div>
      )}

      <section>
        <div className="mb-2 flex items-center justify-between"><h3 className="text-xs font-semibold uppercase tracking-wide text-ink-3">Requirements</h3><span className="text-xs text-ink-3">{asked}/{lead.questions.length}</span></div>
        <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${pct}%` }} /></div>
        {lead.questions.length === 0 ? <div className="text-xs text-ink-3">No question flow — map this lead's form in Forms & flows.</div> : (
          <dl className="divide-y divide-line/70 rounded-xl border border-line">
            {lead.questions.map((qq: any) => {
              const r: any = answered.get(qq.key);
              return (
                <div key={qq.key} className="flex items-center justify-between gap-2 px-3 py-2 text-xs">
                  <dt className="text-ink-3">{qq.label}</dt>
                  <dd className={clsx("text-right", r ? "font-semibold text-ink" : "text-ink-4")}>{r ? r.display : done ? "Not needed" : "Not yet asked"}</dd>
                </div>
              );
            })}
          </dl>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Details</h3>
        <dl className="space-y-1.5 text-xs">
          {[["Property", lead.property?.name || "—"], ["Owner", lead.owner?.name || "Unassigned"], ["Interest (form)", lead.interest || "—"],
            ["Budget (form)", lead.budget_text || "—"], ["City", lead.city || "—"], ["Source", lead.source === "sheet" ? "Meta form via sheet" : lead.source]].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3"><dt className="text-ink-3">{k}</dt><dd className="text-right font-medium text-ink">{v}</dd></div>
          ))}
        </dl>
      </section>

      {conv.state === "handoff" && conv.handoff_reason && (
        <div className="rounded-xl border border-violet-200 bg-violet-50 p-3 text-xs text-violet-900">Handed to a person: <b>{conv.handoff_reason.replace(/_/g, " ")}</b></div>
      )}
    </aside>
  );
}
