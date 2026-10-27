import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowCounterClockwise, ArrowSquareOut, Check, Copy, DeviceMobile, LinkSimple, LockSimple, LockSimpleOpen,
  PhoneCall, Prohibit, ShieldCheck, Translate, Warning, X,
} from "@phosphor-icons/react";
import { HttpError, api, setConsoleKey } from "../api";
import {
  ErrorNote, KeyGate, OutcomeLabel, REQUEST_ICON, VerdictBadge, prefersReducedMotion, scriptLang, useLiveCalls,
  useStage,
} from "../components";
import type { CallView, DemoCustomer, Verdict } from "../types";
import { REQUEST_LABEL } from "../types";
import { CHALLENGE_LABEL, FACTOR_LABEL, decidedBy, elapsed, headline, isVoicePauseRefusal, signalTicks } from "../verdict";
import { BankApp } from "./BankAppPage";

// English first, then Hindi, then Kannada: the order the demo usually runs in. Others follow by name.
const LANGUAGE: Record<string, { rank: number; name: string; native: string }> = {
  en: { rank: 0, name: "English", native: "English" },
  hi: { rank: 1, name: "Hindi", native: "हिन्दी" },
  kn: { rank: 2, name: "Kannada", native: "ಕನ್ನಡ" },
};

/** The demo Customers with their pairing tokens and Voice Pause, polled. A 403 asks for the Console key. */
function useDemoCustomers(keyVersion: number, onLocked: () => void) {
  const [customers, setCustomers] = useState<DemoCustomer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const list = await api.demoCustomers();
      if (!alive.current) return;
      list.sort((a, b) => (LANGUAGE[a.language]?.rank ?? 9) - (LANGUAGE[b.language]?.rank ?? 9) || a.name.localeCompare(b.name));
      setCustomers(list);
      setError(null);
    } catch (e) {
      if (!alive.current) return;
      if (e instanceof HttpError && e.status === 403) onLocked();
      else setError(`The verifier is not answering (${String(e)}). Retrying.`);
    }
  }, [keyVersion]);

  useEffect(() => {
    alive.current = true;
    refresh();
    const id = setInterval(refresh, 2500);
    return () => {
      alive.current = false;
      clearInterval(id);
    };
  }, [refresh]);

  return { customers, error, refresh };
}

/** The Demo hub. With ?stage=1 it is the projector view: the Verdict Ribbon across the top third, the three
 *  Customers' phones below it, the Customer on the latest Call at full strength and the others stepped back,
 *  Possession Codes masked, and every laptop control (pairing links, Call buttons, Reset) hidden. */
export default function DemoPage() {
  const stage = useStage();
  const [keyVersion, setKeyVersion] = useState(0);
  const [locked, setLocked] = useState(false);
  const lock = useCallback(() => setLocked(true), []);
  const { customers, error, refresh } = useDemoCustomers(keyVersion, lock);
  const { list: calls, connected } = useLiveCalls(keyVersion, lock);

  // A Call that just closed may have started a Voice Pause: refresh at once rather than on the next tick.
  const closedCalls = calls.filter((c) => c.state === "closed").length;
  useEffect(() => {
    refresh();
  }, [closedCalls, refresh]);

  if (locked)
    return (
      <KeyGate
        why="The Demo hub shows every Customer's Bank App pairing link and Calls, so it is for bank staff."
        onKey={(key) => {
          setConsoleKey(key);
          setLocked(false);
          setKeyVersion((v) => v + 1);
        }}
      />
    );

  // The Ribbon follows the newest Call and holds its Verdict until the next Call starts.
  const latest = calls[0] ?? null;
  const subject = latest ? customers?.find((c) => c.id === latest.customer.id) : undefined;

  return (
    <div className={`flex flex-col ${stage ? "gap-4" : "gap-6"}`}>
      {!stage && (
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">Demo</h1>
            <p className="mt-1 max-w-2xl text-sm text-ink-soft">
              Every demo Customer on one screen: their Bank App, their Call and their Voice Pause. Place a Call from a
              card, read the Possession Code off that Customer's phone, and lift a Voice Pause here. For the projector,
              open{" "}
              <a href="/demo?stage=1" target="_blank" rel="noopener noreferrer" className="font-medium text-accent underline-offset-4 hover:underline">
                /demo?stage=1
              </a>
              .
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {connected ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-accent/12 px-2.5 py-1 text-xs font-medium text-accent">
                <span className="live-dot" aria-hidden /> Live
              </span>
            ) : (
              <span className="rounded-full bg-block/10 px-2.5 py-1 text-xs font-medium text-block">Reconnecting</span>
            )}
            <Link
              to="/console"
              className="press inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-ink-soft ring-1 ring-line hover:text-ink"
            >
              <ShieldCheck size={16} aria-hidden /> Console
            </Link>
            <ResetDemo onDone={refresh} />
          </div>
        </header>
      )}

      <VerdictRibbon call={latest} name={subject?.name ?? latest?.customer.name ?? ""} stage={stage} connected={connected} />

      <ErrorNote error={error} />

      {!customers && (
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label="Loading Customers">
          {[0, 1, 2].map((i) => <div key={i} className="skeleton h-[40rem] rounded-xl" />)}
        </div>
      )}
      {customers && customers.length === 0 && (
        <p className="rounded-xl border border-line bg-surface p-6 text-sm text-ink-soft">
          No Customers yet. Run <code>pratyaksh-seed</code> on the verifier to add the demo Customers.
        </p>
      )}
      {customers && customers.length > 0 && (
        <div className={`grid md:grid-cols-2 lg:grid-cols-3 ${stage ? "gap-6" : "gap-5"}`}>
          {customers.map((c) => (
            <CustomerCard
              key={c.id}
              customer={c}
              call={calls.find((x) => x.customer.id === c.id) ?? null}
              stage={stage}
              active={latest?.customer.id === c.id}
              dim={stage && !!latest && latest.customer.id !== c.id}
              onChanged={refresh}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ the Verdict Ribbon */

const VERDICT_WORD: Record<Verdict, string> = { PASS: "PASS", STEP_UP: "STEP-UP", BLOCK: "BLOCKED" };
const VERDICT_ICON = { PASS: ShieldCheck, STEP_UP: Warning, BLOCK: Prohibit };

/** Releases a growing count one step at a time, at least `ms` apart, so the room can follow each Signal as
 *  it lands (the Console keeps the true timestamps). Starts at the full count, so a reload shows all at once. */
function useDwell(n: number, ms: number): number {
  const [shown, setShown] = useState(n);
  const last = useRef(0);
  useEffect(() => {
    if (shown >= n) {
      if (shown > n) setShown(n);
      return;
    }
    const wait = Math.max(0, last.current + ms - performance.now());
    const t = window.setTimeout(() => {
      last.current = performance.now();
      setShown((k) => k + 1);
    }, wait);
    return () => window.clearTimeout(t);
  }, [n, shown, ms]);
  return Math.min(shown, n);
}

/** The projector's one large thing: the latest Call, Signal by Signal, then its Verdict. The same layout for
 *  PASS and BLOCK, so the contrast between them carries the story. */
export function VerdictRibbon({ call, name, stage, connected = true }: {
  call: CallView | null;
  name: string;
  stage: boolean;
  connected?: boolean;
}) {
  const pad = stage ? "min-h-[15rem] px-8 py-6" : "min-h-[9rem] px-5 py-4";
  if (!call)
    return (
      <section aria-label="Verdict" aria-live="polite" className={`ribbon flex flex-col justify-center gap-4 rounded-2xl border border-line bg-surface ${pad}`}>
        <p className={`text-ink-soft ${stage ? "text-[2rem]" : "text-xl"}`}>{connected ? "Waiting for a Call" : "Connecting to the verifier…"}</p>
        {stage && <RibbonFooter decided={false} />}
      </section>
    );
  return <RibbonBody key={call.id} call={call} name={name} stage={stage} pad={pad} />;
}

function RibbonBody({ call, name, stage, pad }: { call: CallView; name: string; stage: boolean; pad: string }) {
  const first = name.split(" ")[0] || "the Customer";
  const { ticks, spoof } = signalTicks(call);
  const shown = useDwell(ticks.length, stage && !prefersReducedMotion() ? 450 : 0);
  const decided = call.verdict !== null && shown >= ticks.length;
  const verdict = decided ? call.verdict : null;
  const live = call.state !== "closed";
  const refused = isVoicePauseRefusal(call);
  const by = decided ? decidedBy(call) : null;
  const Glyph = call.request ? REQUEST_ICON[call.request] : PhoneCall;
  const challenge = call.challenges[call.challenges.length - 1];
  const VIcon = verdict ? VERDICT_ICON[verdict] : null;

  return (
    <section
      aria-label="Verdict"
      aria-live="polite"
      data-verdict={verdict ?? undefined}
      className={`ribbon flex flex-col gap-4 rounded-2xl border ${pad} ${
        verdict ? "border-transparent text-on-fill" : "border-line bg-surface text-ink"
      }`}
    >
      {/* who and what */}
      <p className={`flex flex-wrap items-center gap-x-3 gap-y-1 font-medium ${stage ? "text-2xl" : "text-base"} ${verdict ? "text-on-fill/85" : "text-ink-soft"}`}>
        {live ? (
          <span className={`inline-flex items-center gap-2 font-semibold ${verdict ? "" : "text-accent"}`}>
            <span className="live-dot" aria-hidden /> In call
          </span>
        ) : (
          <span className="font-semibold">Call</span>
        )}
        <span aria-hidden>·</span>
        <span className="inline-flex items-center gap-2">
          <Glyph size={stage ? 26 : 18} aria-hidden /> {call.request ? REQUEST_LABEL[call.request] : "Listening for the Request"}
        </span>
        <span className={verdict ? "" : "text-ink"}>as {name}</span>
        <span className="ml-auto font-mono">{elapsed(call.created_at, call.updated_at)}</span>
      </p>

      {/* the Verdict, or the step the Call is on */}
      {verdict && VIcon ? (
        <div className="flex flex-col gap-2">
          <p
            className="ribbon-word flex items-center gap-[0.18em] font-display font-bold leading-[0.95] tracking-[-0.03em]"
            style={{ fontSize: stage ? "var(--text-ribbon)" : "var(--text-ribbon-compact)" }}
          >
            <VIcon weight="fill" className={`size-[0.8em] shrink-0 ${verdict === "PASS" ? "ribbon-icon-spring" : ""}`} aria-hidden />
            {VERDICT_WORD[verdict]}
          </p>
          <p className={`ribbon-word font-medium leading-snug ${stage ? "text-[2rem]" : "text-lg"}`}>{headline(call, first)}</p>
        </div>
      ) : (
        <LiveStep call={call} first={first} stage={stage} challengeOpen={live && call.state === "challenging" && !!challenge} />
      )}

      {/* Signals as they landed; the advisory Spoof Score set apart */}
      {(ticks.length > 0 || spoof !== null) && !refused && (
        <ul className={`flex flex-wrap items-center gap-2 ${stage ? "text-lg" : "text-sm"}`} aria-label="Signals">
          {ticks.slice(0, shown).map((t) => (
            <li
              key={t.key}
              className={`tick inline-flex items-center gap-1.5 rounded-full px-3 py-1 ${
                verdict ? "bg-on-fill/12" : t.ok === false ? "bg-block/12 text-block" : t.ok ? "bg-pass/12 text-pass" : "bg-sunken text-ink-soft"
              }`}
            >
              <span className="tick-mark inline-flex">
                {t.ok === false ? (
                  <X size={stage ? 20 : 15} weight="bold" aria-label="missed" />
                ) : (
                  <Check size={stage ? 20 : 15} weight="bold" aria-label="met" />
                )}
              </span>
              <span className="font-semibold">{t.label}</span>
              <span className="font-mono">{t.value}</span>
              {t.need && <span className="font-mono text-[0.8em] opacity-80">{t.need}</span>}
            </li>
          ))}
          {spoof !== null && shown >= ticks.length && (
            <li
              className={`tick inline-flex items-center gap-1.5 rounded-full border border-dashed px-3 py-1 sm:ml-auto ${
                verdict ? "border-on-fill/50" : "border-line-strong text-ink-soft"
              }`}
              title="The spoof model flags some real whispers, so it never decides a Verdict."
            >
              <span>Spoof Score</span>
              <span className="font-mono">{spoof.toFixed(2)}</span>
              <span className="text-[0.8em]">advisory, not used in the Verdict</span>
            </li>
          )}
        </ul>
      )}

      {by && (
        <p className={`flex flex-wrap items-center gap-3 ${stage ? "text-xl" : "text-sm"}`}>
          <span className="rounded-full bg-on-fill/15 px-3 py-1 font-semibold">Decided by: {FACTOR_LABEL[by]}</span>
          {call.liveness !== null && <span className="font-mono">Liveness {call.liveness.toFixed(2)}</span>}
        </p>
      )}
      {stage && <RibbonFooter decided={!!verdict} />}
    </section>
  );
}

/** While the Call is live: the Challenge it is on, in words the room can follow. */
function LiveStep({ call, first, stage, challengeOpen }: { call: CallView; first: string; stage: boolean; challengeOpen: boolean }) {
  const challenge = call.challenges[call.challenges.length - 1];
  const big = stage ? "text-5xl" : "text-2xl";
  if (call.state === "awaiting_app_approval")
    return <p className={`font-display font-semibold tracking-tight ${big}`}>App Approval: <span className="text-accent">on {first}'s phone</span></p>;
  if (challengeOpen && challenge?.kind === "whisper_phrase")
    return (
      <div key={call.challenges.length} className="motion-enter flex flex-col gap-1">
        <p className={`font-display font-semibold tracking-tight ${big}`}>{CHALLENGE_LABEL.whisper_phrase}</p>
        {challenge.phrase && (
          <p className={`font-display font-semibold text-accent ${stage ? "text-4xl" : "text-xl"}`} lang={scriptLang(challenge.phrase)}>
            “{challenge.phrase}”
          </p>
        )}
      </div>
    );
  if (challengeOpen && challenge?.kind === "possession_code")
    return (
      <p key={call.challenges.length} className={`motion-enter font-display font-semibold tracking-tight ${big}`}>
        {CHALLENGE_LABEL.possession_code}: <span className="text-accent">on {first}'s phone</span>
      </p>
    );
  if (call.state === "closed")
    return <p className={`font-display font-semibold tracking-tight text-ink-soft ${big}`}>Call ended without a Verdict</p>;
  return <p className={`font-display font-semibold tracking-tight text-ink-soft ${big}`}>Listening for the Request</p>;
}

function RibbonFooter({ decided }: { decided: boolean }) {
  return (
    <p className={`mt-auto flex flex-wrap gap-x-8 gap-y-1 text-base ${decided ? "text-on-fill/85" : "text-ink-soft"}`}>
      <span>
        <b className="font-semibold">Live:</b> Calls, Verdicts, phones
      </span>
      <span>
        <b className="font-semibold">Pre-generated:</b> clone audio (IndicF5, consented reference)
      </span>
    </p>
  );
}

/* ------------------------------------------------------------------ one Customer */

function CustomerCard({ customer, call, stage, active, dim, onChanged }: {
  customer: DemoCustomer;
  call: CallView | null;
  stage: boolean;
  active: boolean;
  dim: boolean;
  onChanged: () => void;
}) {
  const live = call !== null && call.state !== "closed";
  const lang = LANGUAGE[customer.language];
  const first = customer.name.split(" ")[0];
  // The ring says what this Customer's latest Call is doing: live (accent), or its Verdict.
  const tone = live ? "accent" : call?.verdict === "BLOCK" ? "block" : call?.verdict === "PASS" ? "pass" : null;
  const ring = { accent: "ring-2 ring-accent", block: "ring-2 ring-block", pass: "ring-2 ring-pass" };
  const text = { accent: "text-accent", block: "text-block", pass: "text-pass" };
  return (
    <section
      aria-label={customer.name}
      className={`tile flex min-w-0 flex-col gap-3 rounded-xl border border-line bg-surface p-4 ${
        tone && (active || !stage) ? ring[tone] : ""
      } ${dim ? "is-dim" : ""}`}
    >
      {/* one arrival ring when this Customer's Call starts or gets its Verdict */}
      {tone && active && <span key={`${call?.id}-${call?.verdict ?? "live"}`} className={`ring-once ${text[tone]}`} aria-hidden />}
      <div className="flex items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-accent/12 font-display text-sm font-semibold text-accent">
          {customer.name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate font-semibold leading-tight">{customer.name}</h2>
          <p className="truncate font-mono text-xs text-ink-soft">{customer.phone_masked}</p>
        </div>
        <span
          className="inline-flex shrink-0 items-center gap-1 rounded-full bg-sunken px-2.5 py-1 text-xs font-medium text-ink"
          title={`Profile language: ${lang?.name ?? customer.language}`}
        >
          <Translate size={14} className="text-ink-soft" aria-hidden />
          {lang ? (
            lang.native === lang.name ? (
              lang.name
            ) : (
              <>
                <span lang={customer.language} className="text-xs">{lang.native}</span>
                <span className="text-ink-soft">{lang.name}</span>
              </>
            )
          ) : (
            customer.language
          )}
        </span>
      </div>

      {!stage && <CallState call={call} />}
      <VoicePause customer={customer} onLifted={onChanged} controls={!stage} />

      <div className="mx-auto w-full max-w-[19rem]">
        <BankApp customer={customer.id} device={customer.device_token} embedded maskCodes={stage} onAlertsDismissed={onChanged} />
      </div>

      {!stage && (
        <div className="mt-auto flex flex-col gap-2">
          <a
            href={`/call?customer=${encodeURIComponent(customer.id)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="press inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-on-accent hover:bg-accent/90"
          >
            <PhoneCall size={18} weight="bold" aria-hidden /> Call as {first}
            <ArrowSquareOut size={14} className="opacity-70" aria-hidden />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
          <PairingLink customer={customer} />
        </div>
      )}
    </section>
  );
}

/** Idle, or in a Call with its Request and current Challenge, and the last Verdict. (On the projector the
 *  Verdict Ribbon carries this.) */
function CallState({ call }: { call: CallView | null }) {
  const live = call !== null && call.state !== "closed";
  const Glyph = call?.request ? REQUEST_ICON[call.request] : PhoneCall;
  const challenge = call?.challenges[call.challenges.length - 1];
  return (
    <div className={`flex min-h-[5.5rem] flex-col justify-center gap-1 rounded-lg px-3 py-2 text-sm ${live ? "bg-accent/10" : "bg-sunken"}`} aria-live="polite">
      {!call && (
        <>
          <p className="font-semibold text-ink-soft">Idle</p>
          <p className="text-xs text-ink-soft">No Calls yet.</p>
        </>
      )}
      {call && live && (
        <div key="live" className="motion-enter flex flex-col gap-1">
          <p className="flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 font-semibold text-accent">
              <span className="live-dot" aria-hidden /> In call
            </span>
            <Time at={call.created_at} />
          </p>
          <p className="flex min-w-0 items-center gap-1.5 text-ink">
            <Glyph size={16} className="shrink-0 text-ink-soft" aria-hidden />
            <span className="truncate">{call.request ? REQUEST_LABEL[call.request] : "Listening for the Request"}</span>
          </p>
          <p className="text-xs text-ink-soft">
            {call.state === "challenging" && challenge ? (
              <>
                Challenge {call.challenges.length}: <span className="font-medium text-ink">{CHALLENGE_LABEL[challenge.kind]}</span>
                {challenge.kind === "whisper_phrase" && challenge.phrase && (
                  <span className="font-medium text-ink" lang={scriptLang(challenge.phrase)}> “{challenge.phrase}”</span>
                )}
                {challenge.kind === "possession_code" && " (on the phone below)"}
              </>
            ) : call.state === "awaiting_app_approval" ? (
              "Waiting for App Approval on the phone below"
            ) : (
              "Waiting for the Caller to say what they need"
            )}
          </p>
        </div>
      )}
      {call && !live && (
        <div key="idle" className="motion-enter flex flex-col gap-1">
          <p className="flex items-center justify-between gap-2">
            <span className="font-semibold text-ink-soft">Idle</span>
            <Time at={call.updated_at} />
          </p>
          <p className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 text-xs text-ink-soft">Last Call</span>
            {call.verdict && <VerdictBadge verdict={call.verdict} />}
            <OutcomeLabel outcome={call.outcome} />
          </p>
          <p className="truncate text-xs text-ink-soft">
            {call.request ? REQUEST_LABEL[call.request] : "No Request"}
            {call.review_status === "pending" && (
              <>
                {" · "}
                <Link to="/console" className="font-medium text-accent underline-offset-2 hover:underline">
                  Agent Review pending
                </Link>
              </>
            )}
          </p>
        </div>
      )}
    </div>
  );
}

function Time({ at }: { at: string }) {
  return (
    <span className="shrink-0 font-mono text-xs text-ink-soft">
      {new Date(at + "Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
    </span>
  );
}

/** Off, or on (the scrim fades in and the lock's shackle drops) with a button that dismisses the Customer's
 *  Security Alerts the way their phone would. On the projector the button is hidden. */
function VoicePause({ customer, onLifted, controls }: { customer: DemoCustomer; onLifted: () => void; controls: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const on = customer.voice_paused;

  async function lift() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.dismissAlerts(customer.id, customer.device_token);
      onLifted();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div key={on ? "on" : "off"} className={`flex h-14 items-center gap-3 rounded-lg px-3 ring-1 ${on ? "pause-scrim ring-block/45" : "ring-line"}`}>
        {on ? (
          <LockSimple size={22} weight="fill" className="shackle shrink-0 text-block" aria-hidden />
        ) : (
          <LockSimpleOpen size={22} className="shrink-0 text-ink-soft" aria-hidden />
        )}
        <div className="min-w-0 flex-1 leading-tight">
          <p className={`text-sm font-semibold ${on ? "text-block" : "text-ink"}`}>Voice Pause {on ? "on" : "off"}</p>
          <p className="truncate text-xs text-ink-soft">
            {on
              ? `${customer.open_security_alerts || 1} Security Alert${customer.open_security_alerts > 1 ? "s" : ""} open${
                  customer.pause_minutes_left !== null ? `, ${Math.ceil(customer.pause_minutes_left)} min left` : ""
                }`
              : "Risky voice Requests are allowed"}
          </p>
        </div>
        {on && controls && (
          <button
            onClick={lift}
            disabled={busy}
            className="press motion-pop shrink-0 rounded-lg bg-ink px-3 py-2 text-xs font-bold text-canvas disabled:opacity-50"
          >
            {busy ? "Lifting…" : "Lift Voice Pause"}
          </button>
        )}
      </div>
      {error && <p className="mt-1 text-xs text-block">{error}</p>}
    </div>
  );
}

/** The Bank App pairing link for a real phone, behind a disclosure: it is the Registered Device's secret. */
function PairingLink({ customer }: { customer: DemoCustomer }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const url = `${window.location.origin}/bank?customer=${encodeURIComponent(customer.id)}&device=${encodeURIComponent(customer.device_token)}`;
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);

  async function copy() {
    try {
      if (!navigator.clipboard) throw new Error("no clipboard API (plain http)");
      await navigator.clipboard.writeText(url);
    } catch {
      input.current?.select();
      document.execCommand("copy");
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="press inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-ink-soft ring-1 ring-line hover:text-ink"
      >
        <DeviceMobile size={17} aria-hidden /> {open ? "Hide phone link" : "Open Bank App on a phone"}
      </button>
      <div
        className={`grid transition-opacity duration-300 ${
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        }`}
        inert={!open}
      >
        <div className="overflow-hidden">
          <div className="mt-2 flex flex-col gap-2 rounded-lg bg-sunken p-3">
            <div className="flex gap-2">
              <label className="sr-only" htmlFor={`pair-${customer.id}`}>Pairing link for {customer.name}</label>
              <input
                id={`pair-${customer.id}`}
                ref={input}
                readOnly
                value={url}
                onFocus={(e) => e.currentTarget.select()}
                className="min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-2 py-1.5 font-mono text-xs text-ink"
              />
              <button
                onClick={copy}
                className="press inline-flex shrink-0 items-center gap-1 rounded-md bg-accent px-2.5 text-xs font-semibold text-on-accent"
              >
                {copied ? <Check size={14} weight="bold" aria-hidden /> : <Copy size={14} aria-hidden />}
                {copied ? "Copied" : "Copy"}
              </button>
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="press grid w-8 shrink-0 place-items-center rounded-md text-ink-soft ring-1 ring-line hover:text-ink"
                aria-label={`Open ${customer.name}'s Bank App in a new tab`}
                title="Open in a new tab"
              >
                <LinkSimple size={15} aria-hidden />
              </a>
            </div>
            <p className="text-xs text-ink-soft">
              {local
                ? "A phone cannot reach localhost. Open this page by the laptop's network address, then copy the link again."
                : `Open it on ${customer.name.split(" ")[0]}'s phone. It pairs that phone as the Registered Device, so keep it private.`}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Between demo runs: dismiss every Security Alert and end Calls left open. Asks once; the Audit Trail
 *  keeps everything (the reset only adds events). */
function ResetDemo({ onDone }: { onDone: () => void }) {
  const [stage, setStage] = useState<"idle" | "confirm" | "busy">("idle");
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!note) return;
    const id = setTimeout(() => setNote(null), 5000);
    return () => clearTimeout(id);
  }, [note]);

  async function reset() {
    setStage("busy");
    try {
      const r = await api.demoReset();
      setNote(
        `${r.dismissed} Security Alert${r.dismissed === 1 ? "" : "s"} dismissed, ${r.ended} open Call${r.ended === 1 ? "" : "s"} ended.`,
      );
      onDone();
    } catch (e) {
      setNote(`Reset failed: ${String(e)}`);
    } finally {
      setStage("idle");
    }
  }

  return (
    <div className="relative">
      {stage === "confirm" ? (
        <div className="motion-pop flex items-center gap-1.5 rounded-lg bg-surface p-1 ring-1 ring-line">
          <span className="px-1.5 text-xs text-ink-soft">End open Calls and dismiss all alerts?</span>
          <button
            onClick={() => setStage("idle")}
            className="press rounded-md px-2.5 py-1 text-xs font-medium text-ink-soft hover:bg-sunken hover:text-ink"
          >
            Cancel
          </button>
          <button onClick={reset} className="press rounded-md bg-ink px-2.5 py-1 text-xs font-semibold text-canvas">
            Reset
          </button>
        </div>
      ) : (
        <button
          onClick={() => setStage("confirm")}
          disabled={stage === "busy"}
          title="Dismiss every Security Alert and end Calls left open. The Audit Trail keeps everything."
          className="press inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-ink-soft ring-1 ring-line hover:text-ink disabled:opacity-50"
        >
          <ArrowCounterClockwise size={16} aria-hidden /> {stage === "busy" ? "Resetting…" : "Reset demo"}
        </button>
      )}
      {note && (
        <p role="status" className="motion-enter absolute right-0 top-full z-10 mt-2 w-max max-w-xs rounded-lg bg-surface px-3 py-2 text-xs text-ink ring-1 ring-line">
          {note}
        </p>
      )}
    </div>
  );
}
