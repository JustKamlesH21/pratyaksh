import type { CSSProperties, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle, CurrencyInr, GearSix, type Icon, Key, LockKey, Prohibit, SimCard, UserPlus, Wallet, Warning, Waveform,
} from "@phosphor-icons/react";
import { api, consoleKey, eventsUrl } from "./api";
import type { CallView, Customer, Outcome, RequestKind, Verdict } from "./types";

export const REQUEST_ICON: Record<RequestKind, Icon> = {
  balance_enquiry: Wallet,
  add_payee: UserPlus,
  sim_swap: SimCard,
  high_value_transfer: CurrencyInr,
  account_service: GearSix,
};

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span
      className="inline-grid shrink-0 place-items-center rounded-lg bg-accent text-on-color"
      style={{ width: size, height: size }}
      aria-hidden
    >
      <Waveform size={size * 0.62} weight="bold" />
    </span>
  );
}

export function Card({ title, children, className = "" }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-line bg-surface p-4 ${className}`}>
      {title && <h2 className="mb-3 text-sm font-semibold text-ink">{title}</h2>}
      {children}
    </section>
  );
}

const verdictStyle: Record<Verdict, [string, Icon]> = {
  PASS: ["bg-pass/10 text-pass ring-pass/30", CheckCircle],
  STEP_UP: ["bg-stepup/10 text-stepup ring-stepup/30", Warning],
  BLOCK: ["bg-block/10 text-block ring-block/30", Prohibit],
};

export function VerdictBadge({ verdict, large = false }: { verdict: Verdict | null; large?: boolean }) {
  if (!verdict) return <span className="text-sm text-ink-soft">pending</span>;
  const [cls, Glyph] = verdictStyle[verdict];
  // Pops in when the Policy decides: the one moment on the Console that matters most.
  return (
    <span
      className={`motion-pop inline-flex items-center gap-1 rounded-full font-bold ring-1 ${cls} ${
        large ? "px-3 py-1 text-sm" : "px-2.5 py-0.5 text-xs"
      }`}
    >
      <Glyph size={large ? 16 : 13} weight="bold" aria-hidden />
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

/** Fades its children up once they scroll into view. Visible at once under reduced motion (CSS). */
export function Reveal({ children, className = "", i = 0, as: Tag = "div" }: {
  children: ReactNode;
  className?: string;
  i?: number;
  as?: "div" | "section" | "li";
}) {
  const ref = useRef<HTMLElement | null>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setSeen(true);
      return;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <Tag
      ref={ref as never}
      className={`reveal ${seen ? "is-visible" : ""} ${className}`}
      style={{ "--i": i } as CSSProperties}
    >
      {children}
    </Tag>
  );
}

export function prefersReducedMotion(): boolean {
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Counts up to `value` when it first arrives or changes (straight to it under reduced motion). */
export function CountUp({ value, decimals = 0, ms = 900 }: { value: number; decimals?: number; ms?: number }) {
  const [shown, setShown] = useState(prefersReducedMotion() ? value : 0);
  const from = useRef(0);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const begin = from.current;
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min(1, (now - start) / ms);
      const eased = 1 - Math.pow(1 - k, 4);
      setShown(begin + (value - begin) * eased);
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return <>{shown.toFixed(decimals)}</>;
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return <p className="rounded-lg bg-block/10 px-3 py-2 text-sm text-block">{error}</p>;
}


/** The live list of Calls over the WebSocket. With CONSOLE_KEY set, the key is the first message;
 *  a refusal (close code 4401) asks the operator for it. */
export function useLiveCalls(keyVersion: number, onLocked: () => void) {
  const [calls, setCalls] = useState<Record<string, CallView>>({});
  const [connected, setConnected] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const connect = () => {
      ws = new WebSocket(eventsUrl());
      ws.onopen = () => {
        ws?.send(JSON.stringify({ key: consoleKey() }));
        setConnected(true);
      };
      ws.onclose = (e) => {
        setConnected(false);
        if (e.code === 4401) {
          onLocked();
          return; // wait for a key, then the effect runs again
        }
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "snapshot") {
          setCalls(Object.fromEntries((msg.calls as CallView[]).map((c) => [c.id, c])));
          setLoaded(true);
        } else if (msg.type === "call") {
          const c = msg.call as CallView;
          // Updates can arrive out of order across server threads; keep the newest.
          setCalls((prev) => (prev[c.id] && prev[c.id].updated_at > c.updated_at ? prev : { ...prev, [c.id]: c }));
        }
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, [keyVersion]);

  const list = useMemo(
    () => Object.values(calls).sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [calls],
  );
  return { list, connected, loaded, setCalls };
}

/** Asks for the verifier's CONSOLE_KEY when a staff read is refused. `why` says what the key unlocks. */
export function KeyGate({ onKey, why = "What Callers said and each Customer's risk are for bank staff." }: {
  onKey: (key: string) => void;
  why?: string;
}) {
  const [key, setKey] = useState("");
  const tried = consoleKey() !== "";
  return (
    <div className="mx-auto mt-16 max-w-md">
      <Card>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            onKey(key);
          }}
        >
          <span className="grid size-11 place-items-center rounded-xl bg-accent/12 text-accent">
            <LockKey size={24} />
          </span>
          <div>
            <h1 className="font-display text-2xl font-semibold tracking-tight">Console key</h1>
            <p className="mt-1 text-sm text-ink-soft">
              {why} Enter the verifier's <code>CONSOLE_KEY</code>.
            </p>
          </div>
          {tried && <p className="text-sm font-medium text-block">That key was not accepted.</p>}
          <input
            type="password"
            autoFocus
            aria-label="Console key"
            className="rounded-lg border border-line bg-canvas px-3 py-2"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <button className="press inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 font-semibold text-on-color">
            <Key size={18} /> Unlock
          </button>
        </form>
      </Card>
    </div>
  );
}
