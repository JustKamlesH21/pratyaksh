import type { CSSProperties, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle, CurrencyInr, GearSix, type Icon, Key, LockKey, Prohibit, SimCard, UserPlus, Wallet, Warning,
} from "@phosphor-icons/react";
import { Link, useLocation } from "react-router-dom";
import { api, consoleKey, eventsUrl } from "./api";
import type { CallView, Customer, Outcome, RequestKind, Verdict } from "./types";

export const REQUEST_ICON: Record<RequestKind, Icon> = {
  balance_enquiry: Wallet,
  add_payee: UserPlus,
  sim_swap: SimCard,
  high_value_transfer: CurrencyInr,
  account_service: GearSix,
};

/** The Pratyaksh mark, "Aksha": प्रत्यक्ष is "before the eye", so an eye whose pupil is a voice, on the bank's
 *  navy. The red centre line is the one live Signal that counts. Detail follows size: five bars from 40 px,
 *  three in the header, one at favicon size (drawn on the Claude Design canvas, Oct 30). */
export function Logo({ size = 28 }: { size?: number }) {
  const bars: [number, number][] = size >= 40 ? [[14.7, 4], [18.7, 8], [26.7, 8], [30.7, 4]] : size >= 22 ? [[18.7, 8], [26.7, 8]] : [];
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" className="shrink-0" aria-hidden>
      <rect width="48" height="48" rx="14" className="fill-brand" />
      <rect x="0.5" y="0.5" width="47" height="47" rx="13.5" fill="none" className="stroke-on-fill/12" />
      <path
        d="M6.5 24C12.5 14.5 35.5 14.5 41.5 24C35.5 33.5 12.5 33.5 6.5 24Z"
        fill="none"
        className="stroke-on-fill"
        strokeWidth={size < 22 ? 3.4 : 2.6}
        strokeLinejoin="round"
      />
      {bars.map(([x, h]) => (
        <rect key={x} x={x} y={24 - h / 2} width="2.6" height={h} rx="1.3" className="fill-on-fill" />
      ))}
      {size < 22 ? (
        <rect x="22.2" y="16" width="3.6" height="16" rx="1.8" className="fill-brand-red" />
      ) : (
        <rect x="22.7" y="17" width="2.6" height="14" rx="1.3" className="fill-brand-red" />
      )}
    </svg>
  );
}

export function Card({ title, children, className = "" }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`elev-1 rounded-2xl border border-line bg-surface p-5 ${className}`}>
      {title && <h2 className="mb-3 text-sm font-semibold text-ink">{title}</h2>}
      {children}
    </section>
  );
}

/** The top of every staff page: the title, one line on what it is for, and the page's actions on the right
 *  (one solid button at most). Kept short: these are screens people work in, and the data should lead. */
export function PageHeader({ title, children, actions }: {
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 border-b border-line pb-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-2xl font-semibold leading-[1.1] tracking-[-0.02em] sm:text-3xl">{title}</h1>
        {children && <div className="max-w-3xl text-sm leading-relaxed text-ink-soft">{children}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Live connection state as a pill: accent with a live dot when connected (never PASS green). */
export function LivePill({ connected }: { connected: boolean }) {
  return connected ? (
    <span className="inline-flex min-h-8 items-center gap-2 rounded-full bg-accent/12 px-3 text-xs font-semibold text-accent">
      <span className="live-dot" aria-hidden /> Live
    </span>
  ) : (
    <span className="inline-flex min-h-8 items-center rounded-full bg-block/10 px-3 text-xs font-semibold text-block">Reconnecting</span>
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
  handed_to_agent: ["Handed to officer", "text-ink"],
  ended: ["Ended (questions only)", "text-ink-soft"],
  abandoned: ["Abandoned", "text-ink-soft"],
};

export function OutcomeLabel({ outcome }: { outcome: Outcome | null }) {
  if (!outcome)
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-accent">
        <span className="live-dot" aria-hidden /> In call
      </span>
    );
  const [text, cls] = outcomeText[outcome];
  return <span className={`text-xs font-semibold ${cls}`}>{text}</span>;
}

/** A 0..1 meter for one Signal. `good` says whether high values are good (Task Match) or bad.
 *  A missed threshold is drawn in block; a met one stays neutral, so the Verdict keeps the only strong
 *  colour. `advisory` (the Spoof Score) is never pass or block and is labelled as not deciding anything.
 *  A Signal that was not measured is a hatched strip, never a silent zero. */
export function Meter({ label, value, good = true, threshold, suffix, missed = good ? "below" : "above", advisory = false }: {
  label: string;
  value: number | null;
  good?: boolean;
  threshold?: number;
  suffix?: string;
  missed?: string;
  advisory?: boolean;
}) {
  const v = value ?? 0;
  const ok = advisory || value === null || threshold === undefined ? null : good ? v >= threshold : v < threshold;
  const color = ok === false ? "bg-block" : "bg-advisory";
  return (
    <div className="grid grid-cols-[7.5rem_1fr_4.5rem] items-center gap-x-2 gap-y-0.5 text-sm">
      <span className="text-ink-soft">{label}</span>
      <div className="relative">
        <div className={`h-2 overflow-hidden rounded-full ${value === null ? "not-measured" : "bg-sunken"}`}>
          {/* grows in when the Signal is measured; scaleX, not width, so no layout work */}
          {value !== null && (
            <div
              className={`motion-grow h-full origin-left ${color}`}
              style={{ transform: `scaleX(${Math.max(0, Math.min(1, v))})` }}
            />
          )}
        </div>
        {threshold !== undefined && !advisory && (
          <div className="absolute -top-1 h-4 w-0.5 rounded-full bg-ink/60" style={{ left: `${threshold * 100}%` }} title={`threshold ${threshold}`} />
        )}
      </div>
      <span className="text-right font-mono text-xs">
        {value === null ? "not measured" : suffix ?? v.toFixed(2)}
        {ok !== null && <span className={ok ? "text-ink-soft" : "font-semibold text-block"}> {ok ? "meets" : missed}</span>}
      </span>
      {advisory && (
        <span className="col-start-2 col-end-4 text-xs text-ink-soft">advisory · flags some real whispers, not used in the Verdict</span>
      )}
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
        className="field"
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

/** Stage mode from a query string: ?stage=1 (125% type) or ?stage=small (112.5%, a 1280x800 projector). */
export function stageOf(search: string): "1" | "small" | null {
  const v = new URLSearchParams(search).get("stage");
  if (!v || v === "0") return null;
  return v === "small" ? "small" : "1";
}

/** True on a page opened for the projector (?stage=1). */
export function useStage(): boolean {
  return stageOf(useLocation().search) !== null;
}

/** Reduced motion from the OS, or html[data-motion="reduce"] (localStorage "motion" = "reduce"). */
export function prefersReducedMotion(): boolean {
  if (typeof document !== "undefined" && document.documentElement.dataset.motion === "reduce") return true;
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** "hi" or "kn" when the text has Devanagari or Kannada letters, for the element's lang attribute (Indic
 *  line-height, no tracking, the right Noto face for screen readers). Mixed Hindi and English is "hi". */
export function scriptLang(text?: string | null): "hi" | "kn" | undefined {
  if (!text) return undefined;
  if (/[ಀ-೿]/.test(text)) return "kn";
  if (/[ऀ-ॿ]/.test(text)) return "hi";
  return undefined;
}

/** A live number. When the value changes, the new one crossfades in (150 ms); no counting up, no rolling
 *  digits, so what is on screen is always a real reading. */
export function LiveNumber({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const text = value.toFixed(decimals);
  return (
    <span key={text} className="motion-fade">
      {text}
    </span>
  );
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return <p className="rounded-xl bg-block/10 px-3.5 py-2.5 text-sm text-block">{error}</p>;
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
              {why} Ask the Pratyaksh team for the key (the verifier’s <code>CONSOLE_KEY</code>).
            </p>
          </div>
          {tried && <p className="text-sm font-medium text-block">That key was not accepted.</p>}
          <input
            type="password"
            autoFocus
            aria-label="Console key"
            className="field bg-canvas"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <button className="btn btn-primary btn-lg">
            <Key size={18} /> Use this key
          </button>
          <p className="text-center text-sm text-ink-soft">
            No key? <Link to="/call" className="font-medium text-accent underline-offset-4 hover:underline">Place a test call</Link>
          </p>
        </form>
      </Card>
    </div>
  );
}
