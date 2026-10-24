import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { api } from "./api";
import type { Customer, Outcome, Verdict } from "./types";

export function Card({ title, children, className = "" }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-line bg-surface p-4 ${className}`}>
      {title && <h2 className="mb-3 text-sm font-semibold text-ink">{title}</h2>}
      {children}
    </section>
  );
}

const verdictStyle: Record<Verdict, string> = {
  PASS: "bg-pass/10 text-pass ring-pass/30",
  STEP_UP: "bg-stepup/10 text-stepup ring-stepup/30",
  BLOCK: "bg-block/10 text-block ring-block/30",
};

export function VerdictBadge({ verdict }: { verdict: Verdict | null }) {
  if (!verdict) return <span className="text-sm text-ink-soft">pending</span>;
  // Pops in when the Policy decides: the one moment on the Console that matters most.
  return (
    <span className={`motion-pop inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${verdictStyle[verdict]}`}>
      {verdict === "STEP_UP" ? "STEP-UP" : verdict}
    </span>
  );
}

const outcomeText: Record<Outcome, [string, string]> = {
  passed: ["Passed", "text-pass"],
  passed_pending_review: ["Passed, in review", "text-pass"],
  approved_in_app: ["Approved in app", "text-pass"],
  blocked: ["Blocked", "text-block"],
  declined_in_app: ["Declined in app", "text-block"],
  handed_to_agent: ["Handed to officer", "text-stepup"],
  ended: ["Ended (questions only)", "text-ink-soft"],
  abandoned: ["Abandoned", "text-ink-soft"],
};

export function OutcomeLabel({ outcome }: { outcome: Outcome | null }) {
  if (!outcome)
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-accent">
        <span className="live-dot" aria-hidden /> Live
      </span>
    );
  const [text, cls] = outcomeText[outcome];
  return <span className={`text-xs font-semibold ${cls}`}>{text}</span>;
}

/** A 0..1 meter. `good` says whether high values are good (task match) or bad (spoof score). */
export function Meter({ label, value, good = true, threshold, suffix }: {
  label: string;
  value: number | null;
  good?: boolean;
  threshold?: number;
  suffix?: string;
}) {
  const v = value ?? 0;
  const ok = value === null ? null : threshold === undefined ? null : good ? v >= threshold : v < threshold;
  const color = ok === null ? "bg-ink-soft" : ok ? "bg-pass" : "bg-block";
  return (
    <div className="grid grid-cols-[7.5rem_1fr_4.5rem] items-center gap-2 text-sm">
      <span className="text-ink-soft">{label}</span>
      <div className="relative">
        <div className="h-2 overflow-hidden rounded-full bg-sunken">
          {/* grows in when the Signal is measured; scaleX, not width, so no layout work */}
          {value !== null && (
            <div
              className={`motion-grow h-full origin-left motion-safe:transition-transform motion-safe:duration-500 ${color}`}
              style={{ transform: `scaleX(${Math.max(0, Math.min(1, v))})` }}
            />
          )}
        </div>
        {threshold !== undefined && (
          <div className="absolute -top-1 h-4 w-0.5 rounded-full bg-ink/60" style={{ left: `${threshold * 100}%` }} title={`threshold ${threshold}`} />
        )}
      </div>
      <span className="text-right font-mono text-xs">
        {value === null ? "n/a" : suffix ?? v.toFixed(2)}
        {ok !== null && <span className={ok ? "text-pass" : "text-block"}> {ok ? "ok" : "low"}</span>}
      </span>
    </div>
  );
}

export function useCustomers(): Customer[] {
  const [customers, setCustomers] = useState<Customer[]>([]);
  useEffect(() => {
    api.customers().then(setCustomers).catch(() => setCustomers([]));
  }, []);
  return customers;
}

export function CustomerPicker({ value, onChange, label = "Customer" }: {
  value: string;
  onChange: (id: string) => void;
  label?: string;
}) {
  const customers = useCustomers();
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-ink-soft">{label}</span>
      <select
        className="rounded-lg border border-line bg-surface px-3 py-2 text-ink"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Choose…</option>
        {customers.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name} ({c.phone_masked})
          </option>
        ))}
      </select>
    </label>
  );
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return <p className="rounded-lg bg-block/10 px-3 py-2 text-sm text-block">{error}</p>;
}
