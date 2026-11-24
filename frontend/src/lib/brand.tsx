// Product identity — change the name here and it updates everywhere in the app.
export const BRAND = {
  name: "LeadNest",
  first: "Lead",
  second: "Nest",
  tagline: "Real-estate lead CRM",
};

/** Logo mark: the "L ▷" arrow on brand green. */
export function LogoMark({ size = 36, className = "" }: { size?: number; className?: string }) {
  return (
    <div style={{ width: size, height: size }} className={`flex shrink-0 items-center justify-center rounded-[10px] bg-gradient-to-br from-brand-500 to-brand-700 ${className}`}>
      <svg viewBox="0 0 24 24" style={{ width: size * 0.5, height: size * 0.5 }} className="text-white" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M4 18V6M4 18h8M14 6l6 6-6 6" />
      </svg>
    </div>
  );
}

/** Wordmark: "Lead" in ink, "Nest" in brand green. */
export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`font-semibold tracking-[-0.03em] ${className}`}>
      <span className="text-ink">{BRAND.first}</span><span className="text-brand-700">{BRAND.second}</span>
    </span>
  );
}
