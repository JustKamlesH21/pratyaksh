import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { api } from "./api";
import type { Customer, Outcome, Verdict } from "./types";

export function Card({ title, children, className = "" }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-ink/10 bg-white p-4 shadow-sm ${className}`}>
      {title && <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-ink-soft">{title}</h2>}
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
  if (!verdict) return <span className="text-sm text-ink-soft/60">pending</span>;
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${verdictStyle[verdict]}`}>
      {verdict === "STEP_UP" ? "STEP-UP" : verdict}
    </span>
  );
}

const outcomeText: Record<Outcome, [string, string]> = {
  passed: ["Passed", "text-pass"],
  passed_pending_review: ["Passed · review", "text-pass"],
  approved_in_app: ["Approved in app", "text-pass"],
  blocked: ["Blocked", "text-block"],
  declined_in_app: ["Declined in app", "text-block"],
  abandoned: ["Abandoned", "text-ink-soft/70"],
};

export function OutcomeLabel({ outcome }: { outcome: Outcome | null }) {
  if (!outcome) return <span className="text-xs font-semibold text-violet">● live</span>;
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
  const color = ok === null ? "bg-violet" : ok ? "bg-pass" : "bg-block";
  return (
    <div className="grid grid-cols-[7.5rem_1fr_4.5rem] items-center gap-2 text-sm">
      <span className="text-ink-soft">{label}</span>
      <div className="relative h-2.5 rounded-full bg-ink/10">
        {value !== null && <div className={`h-2.5 rounded-full ${color}`} style={{ width: `${Math.round(v * 100)}%` }} />}
        {threshold !== undefined && (
          <div className="absolute -top-1 h-4.5 w-0.5 bg-ink/50" style={{ left: `${threshold * 100}%` }} title={`threshold ${threshold}`} />
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
        className="rounded-lg border border-ink/20 bg-white px-3 py-2"
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
