import { type CSSProperties, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, ArrowUpRight, Broadcast, ChartBar, ChatsCircle, DeviceMobile, Gavel, type Icon, LinkSimple,
  LockKey, Pause, Phone, Play, SealCheck, ShieldCheck, Siren, Translate, Waveform,
} from "@phosphor-icons/react";
import { api } from "../api";
import { CountUp, Logo, Reveal, VerdictBadge, prefersReducedMotion } from "../components";
import type { EvalRun, Stats, Verdict } from "../types";

/* ------------------------------------------------------------------ the hero's simulated Call */

type Mode = "idle" | "voiced" | "whisper" | "clone";

interface Scene {
  step: "Request" | "Whisper Phrase" | "Possession Code" | "Verdict";
  who: "Customer" | "Clone";
  mode: Mode;
  agent?: string;
  caller?: string;
  tag?: string;
  signals?: { task: number; whisper: number; latency: number; spoof: number };
  code?: string;
  verdict?: Verdict;
  liveness?: number;
  note?: string;
  ms: number;
}

// Illustrative values, labelled "Simulation" on the page; live numbers are further down.
const SCENES: Scene[] = [
  { step: "Request", who: "Customer", mode: "voiced", agent: "How can I help you today?", caller: "naya payee add karna hai", tag: "हिन्दी · Request", ms: 2600 },
  { step: "Whisper Phrase", who: "Customer", mode: "idle", agent: "Please whisper these words: friday three baje match.", ms: 2100 },
  { step: "Whisper Phrase", who: "Customer", mode: "whisper", caller: "friday 3 baje match", tag: "whispered", signals: { task: 0.96, whisper: 0.91, latency: 640, spoof: 0.04 }, ms: 2900 },
  { step: "Possession Code", who: "Customer", mode: "idle", agent: "Please read out the code on your bank app.", code: "481927", ms: 2100 },
  { step: "Possession Code", who: "Customer", mode: "voiced", caller: "4 8 1 9 2 7", tag: "matches the Registered Device", code: "481927", ms: 2200 },
  { step: "Verdict", who: "Customer", mode: "idle", verdict: "PASS", liveness: 0.93, note: "Verification Receipt signed (Ed25519)", ms: 3200 },
  { step: "Whisper Phrase", who: "Clone", mode: "idle", agent: "Please whisper these words: sanje five baje dinner.", ms: 2000 },
  { step: "Whisper Phrase", who: "Clone", mode: "clone", caller: "sanje 5 baje dinner", tag: "spoken, not whispered", signals: { task: 0.94, whisper: 0.08, latency: 3100, spoof: 0.97 }, ms: 3000 },
  { step: "Verdict", who: "Clone", mode: "idle", verdict: "BLOCK", liveness: 0.21, note: "Security Alert sent · Voice Pause on", ms: 3400 },
];
const STEPS = ["Request", "Whisper Phrase", "Possession Code", "Verdict"] as const;
const BARS = 48;

/** Bar heights for one frame. Voiced speech is loud with syllable bursts; a whisper is low and noisy;
 *  the Clone's "whisper" is a full, too-regular voice. Written straight to the DOM, not React state. */
function heights(mode: Mode, t: number, prev: number[]): number[] {
  return prev.map((p, i) => {
    let target: number;
    if (mode === "voiced") {
      const syllable = 0.55 + 0.45 * Math.sin(t * 7.3 + i * 0.21) * Math.sin(t * 2.1 + i * 0.05);
      target = 0.25 + 0.7 * Math.abs(syllable) * (0.6 + 0.4 * Math.sin(i * 0.9 + t * 11));
    } else if (mode === "whisper") {
      target = 0.1 + Math.random() * 0.26;
    } else if (mode === "clone") {
      target = 0.5 + 0.32 * Math.sin(t * 4 + i * 0.32);
    } else {
      target = 0.05 + 0.03 * Math.sin(t * 2 + i * 0.4);
    }
    return p + (Math.max(0.04, Math.min(1, target)) - p) * (mode === "whisper" ? 0.35 : 0.18);
  });
}

function VerifyDemo() {
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(true);
  const bars = useRef<(HTMLSpanElement | null)[]>([]);
  const card = useRef<HTMLDivElement>(null);
  const scene = SCENES[i];
  const modeRef = useRef<Mode>(scene.mode);
  modeRef.current = scene.mode;

  // Next scene on a timer (pausable: auto-advancing content must be stoppable).
  useEffect(() => {
    if (!playing) return;
    const id = setTimeout(() => setI((n) => (n + 1) % SCENES.length), scene.ms);
    return () => clearTimeout(id);
  }, [i, playing, scene.ms]);

  // The waveform: one rAF loop, paused off-screen, when the tab is hidden, or under reduced motion.
  useEffect(() => {
    let h = Array.from({ length: BARS }, () => 0.06);
    const paint = () => bars.current.forEach((el, k) => el && (el.style.transform = `scaleY(${h[k].toFixed(3)})`));
    if (prefersReducedMotion()) {
      h = heights(modeRef.current === "idle" ? "idle" : "clone", 1, h.map(() => 0.4));
      paint();
      return;
    }
    let visible = true;
    const io = new IntersectionObserver(([e]) => (visible = e.isIntersecting));
    if (card.current) io.observe(card.current);
    let raf = 0;
    const loop = (now: number) => {
      if (visible && !document.hidden) {
        h = heights(modeRef.current, now / 1000, h);
        paint();
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
    };
  }, []);

  // The conversation so far in this Call (the Customer's, then the Clone's), newest last.
  const callStart = SCENES.findIndex((s) => s.who === scene.who);
  const chat = SCENES.slice(callStart, i + 1)
    .flatMap((s, k) => [
      ...(s.agent ? [{ id: `a${callStart + k}`, agent: true, text: s.agent, tag: undefined }] : []),
      ...(s.caller ? [{ id: `c${callStart + k}`, agent: false, text: s.caller, tag: s.tag }] : []),
    ])
    .slice(scene.signals ? -2 : -3); // the Signal strip takes a line's room
  const tone = scene.verdict === "PASS" ? "bg-pass" : scene.verdict === "BLOCK" ? "bg-block" : scene.mode === "idle" ? "bg-ink-soft/40" : "bg-accent";
  const stepIndex = STEPS.indexOf(scene.step);
  return (
    <div
      ref={card}
      className="relative overflow-hidden rounded-2xl border border-line bg-surface/90 shadow-[0_30px_80px_-40px_color-mix(in_oklab,var(--color-accent)_55%,transparent)] backdrop-blur"
    >
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <span className={`live-dot ${scene.who === "Clone" ? "text-block" : "text-pass"}`} aria-hidden />
        <div className="min-w-0 text-sm">
          <p className="font-semibold">
            {scene.who === "Clone" ? "Clone posing as Ananya" : "Ananya, the real Customer"}
          </p>
          <p className="text-xs text-ink-soft">Add payee · Simulation</p>
        </div>
        <button
          className="press ml-auto grid size-8 place-items-center rounded-lg text-ink-soft ring-1 ring-line hover:text-ink"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? "Pause the simulation" : "Play the simulation"}
        >
          {playing ? <Pause size={15} weight="fill" /> : <Play size={15} weight="fill" />}
        </button>
      </div>

      <ol className="grid grid-cols-4 gap-1 px-4 pt-3" aria-label="Verification steps">
        {STEPS.map((s, k) => (
          <li key={s} className="flex flex-col gap-1.5">
            <span className={`h-1 rounded-full transition-colors duration-500 ${k <= stepIndex ? (scene.verdict === "BLOCK" || (scene.who === "Clone" && k === stepIndex) ? "bg-block" : "bg-accent") : "bg-line"}`} />
            <span className={`truncate text-[0.68rem] font-medium ${k === stepIndex ? "text-ink" : "text-ink-soft"}`}>{s}</span>
          </li>
        ))}
      </ol>

      <div className="relative mx-4 mt-4 flex h-24 items-center gap-[3px] overflow-hidden rounded-xl bg-sunken px-3" aria-hidden>
        {Array.from({ length: BARS }, (_, k) => (
          <span
            key={k}
            ref={(el) => {
              bars.current[k] = el;
            }}
            className={`h-full flex-1 origin-center rounded-full transition-colors duration-500 ${tone}`}
            style={{ transform: "scaleY(0.06)" }}
          />
        ))}
        {scene.mode !== "idle" && (
          <span className="scan-line pointer-events-none absolute inset-y-0 left-0 w-[10%] bg-gradient-to-r from-transparent via-accent/25 to-transparent" />
        )}
      </div>

      <div className="relative flex h-[17rem] flex-col justify-end gap-2.5 overflow-hidden p-4" aria-live="polite">
        {chat.map((line) =>
          line.agent ? (
            <p key={line.id} className="motion-enter flex max-w-[85%] items-start gap-2 rounded-2xl rounded-tl-sm bg-sunken px-3 py-2 text-sm">
              <Waveform size={16} className="mt-0.5 shrink-0 text-accent" />
              {line.text}
            </p>
          ) : (
            <div key={line.id} className="motion-enter ml-auto flex max-w-[85%] flex-col items-end gap-1">
              <p className="rounded-2xl rounded-tr-sm bg-accent/12 px-3 py-2 text-sm ring-1 ring-accent/25">{line.text}</p>
              {line.tag && <span className="text-[0.7rem] font-medium text-ink-soft">{line.tag}</span>}
            </div>
          ),
        )}
        {scene.code && !scene.caller && (
          <div key={`d${i}`} className="motion-pop mx-auto flex items-center gap-3 rounded-xl border border-line bg-canvas px-4 py-2">
            <DeviceMobile size={22} className="text-accent" />
            <span className="font-mono text-2xl tracking-[0.3em]">{scene.code}</span>
          </div>
        )}
        {scene.signals && <SignalStrip key={`s${i}`} s={scene.signals} />}
        {scene.verdict && (
          <div key={`v${i}`} className="absolute inset-0 grid place-items-center bg-surface/80 backdrop-blur-sm">
            <div className="motion-pop flex flex-col items-center gap-2 text-center">
              <VerdictBadge verdict={scene.verdict} large />
              <p className="font-mono text-sm text-ink-soft">liveness {scene.liveness?.toFixed(2)}</p>
              <p className={`text-sm font-medium ${scene.verdict === "PASS" ? "text-pass" : "text-block"}`}>{scene.note}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SignalStrip({ s }: { s: NonNullable<Scene["signals"]> }) {
  const rows: [string, number, boolean, string][] = [
    ["Task Match", s.task, s.task >= 0.7, s.task.toFixed(2)],
    ["Whisper Score", s.whisper, s.whisper >= 0.6, s.whisper.toFixed(2)],
    ["Reply Latency", Math.max(0, Math.min(1, 1 - (s.latency - 1200) / 1800)), s.latency <= 1200, `${s.latency} ms`],
    ["Spoof Score", s.spoof, s.spoof < 0.85, s.spoof.toFixed(2)],
  ];
  return (
    <div className="motion-enter grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-xl bg-sunken/60 p-3 text-xs">
      {rows.map(([label, v, ok, shown], k) => (
        <div key={label} className="flex flex-col gap-1">
          <span className="flex justify-between text-ink-soft">
            {label} <b className={`font-mono ${ok ? "text-pass" : "text-block"}`}>{shown}</b>
          </span>
          <span className="h-1 overflow-hidden rounded-full bg-line">
            <span
              className={`motion-grow block h-full origin-left rounded-full ${ok ? "bg-pass" : "bg-block"}`}
              style={{ transform: `scaleX(${v})`, animationDelay: `${k * 90}ms` } as CSSProperties}
            />
          </span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ live numbers */

function LiveNumbers() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    api.stats().then(setStats).catch(() => setOffline(true));
    api.latestEval().then(setRun).catch(() => undefined);
  }, []);
  if (offline)
    return <p className="text-sm text-ink-soft">Start the verifier to see live numbers from this machine.</p>;
  if (!stats)
    return (
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4" aria-busy="true">
        {[0, 1, 2, 3].map((k) => <div key={k} className="skeleton h-24" />)}
      </div>
    );
  const tiles: [string, number | null, number, string, string][] = [
    ["Calls verified", stats.calls, 0, "", "on this verifier"],
    ["Calls blocked", stats.blocked, 0, "", "Clones and failed checks"],
    ["Added Time", stats.avg_added_seconds, 1, " s", "for genuine Callers"],
    ["Hearing a Response", stats.hearing_ms.p50, 0, " ms", "median, speech models + understanding"],
  ];
  if (run?.summary.catch_rate != null)
    tiles.push(["Catch Rate", run.summary.catch_rate * 100, 0, "%", `latest Eval Run, ${run.summary.clone_calls} Clone Calls`]);
  if (run?.summary.false_reject_rate != null)
    tiles.push(["False Reject Rate", run.summary.false_reject_rate * 100, 0, "%", `${run.summary.real_calls} real Calls`]);
  return (
    <div className={`grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line ${tiles.length > 4 ? "md:grid-cols-3" : "md:grid-cols-4"}`}>
      {tiles.map(([label, value, decimals, unit, hint], k) => (
        <Reveal key={label} i={k} className="flex flex-col gap-1 bg-surface p-5">
          <span className="text-xs font-medium text-ink-soft">{label}</span>
          <span className="font-display text-3xl font-semibold tracking-tight md:text-4xl">
            {value === null ? "-" : <CountUp value={value} decimals={decimals} />}
            {value !== null && <span className="text-xl text-ink-soft">{unit}</span>}
          </span>
          <span className="text-xs text-ink-soft">{hint}</span>
        </Reveal>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ page */

const HOW: [Icon, string, string][] = [
  [ChatsCircle, "Hear the Request", "The Voice Agent understands what the Caller wants, in English, Hindi or Kannada, and the Policy sets the Risk Tier. Questions get answers along the way."],
  [Waveform, "Whisper Phrase", "A random phrase, whispered back. Task Match, Whisper Score, Reply Latency and a spoof model score every Response."],
  [DeviceMobile, "Possession Code", "Six digits on the Customer's Registered Device. A perfect voice clone still does not hold the phone."],
  [SealCheck, "Verdict and receipt", "PASS, STEP-UP or BLOCK with plain-language Reasons. Core banking redeems a signed Verification Receipt once."],
];

const DEFENCES: [Icon, string, string, string][] = [
  [Gavel, "The LLM never decides", "Keyword rules and an LLM work out what the Caller means. Only the Policy sets a Verdict, and LLM replies with numbers, outcome claims or asks for an OTP are dropped before they are spoken.", "md:col-span-2 md:row-span-2"],
  [Siren, "Security Alert and Voice Pause", "Every BLOCK alerts the Customer's phone, and risky voice Requests pause until they dismiss it.", ""],
  [Broadcast, "Attack Wave", "Blocked Calls for 3 Customers within 15 minutes put a Bank Agent on every risky Request.", ""],
  [LinkSimple, "Tamper-evident Audit Trail", "Insert-only and hash-chained. Edit one event and the Console shows exactly where.", ""],
  [Translate, "Transcripts in three languages", "Both sides of the Call with Signals and timings, downloadable with the Audit head.", ""],
  [LockKey, "No voice biometrics", "No voiceprint is enrolled or stored. Audio is scored in memory and discarded.", "md:col-span-2"],
  [SealCheck, "Receipts redeemed once", "An Ed25519-signed Verification Receipt says whether core banking may act, and works once per Call.", "md:col-span-2"],
];

const PLACES: [Icon, string, string, string][] = [
  [ShieldCheck, "/console", "Console", "Live Calls, Signals, Verdicts, Transcripts and Agent Review."],
  [Phone, "/call", "Caller", "Call the Voice Agent from this browser."],
  [DeviceMobile, "/bank", "Bank App", "The Registered Device: codes, approvals and Security Alerts."],
  [ChartBar, "/eval", "Eval", "Catch Rate and False Reject Rate from recorded Calls."],
];

export default function LandingPage() {
  return (
    <div className="overflow-x-clip">
      <section className="relative">
        <div className="dot-grid pointer-events-none absolute inset-0" aria-hidden />
        <div className="glow pointer-events-none absolute -inset-x-1/4 -top-1/3 bottom-0" aria-hidden />
        <div className="relative mx-auto grid min-h-[calc(100dvh-3.5rem)] max-w-7xl items-center gap-12 px-4 py-14 lg:grid-cols-[1.05fr_1fr] lg:py-10">
          <div className="flex flex-col items-start gap-6">
            <span className="motion-enter inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 px-3 py-1 text-xs font-medium text-ink-soft">
              <span className="live-dot text-accent" aria-hidden />
              FET Aavishkar 2026 · Cybersecurity · Team Omnitrons
            </span>
            <h1 className="motion-enter font-display text-[2.6rem] font-semibold leading-[1.04] tracking-[-0.035em] sm:text-6xl md:text-7xl" style={{ "--i": 1 } as CSSProperties}>
              Voice clones sound like anyone.
              <span className="block text-accent">Pratyaksh checks for a live person.</span>
            </h1>
            <p className="motion-enter max-w-[58ch] text-base leading-relaxed text-ink-soft md:text-lg" style={{ "--i": 2 } as CSSProperties}>
              Before a bank acts on a risky phone Request, the Voice Agent asks the Caller to whisper a random phrase
              and read a one-time code from their Registered Device. The Policy turns what it measures into PASS,
              STEP-UP or BLOCK, with plain-language Reasons. No voiceprint is ever stored.
            </p>
            <div className="motion-enter flex flex-wrap gap-3" style={{ "--i": 3 } as CSSProperties}>
              <Link to="/console" className="press group inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-3 font-semibold text-on-color">
                Open the Console
                <ArrowRight size={18} weight="bold" className="nudge" />
              </Link>
              <Link to="/call" className="press inline-flex items-center gap-2 rounded-xl bg-surface px-5 py-3 font-semibold ring-1 ring-line hover:ring-accent/50">
                <Phone size={18} /> Place a test call
              </Link>
            </div>
            <ul className="motion-enter flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink-soft" style={{ "--i": 4 } as CSSProperties}>
              <li className="flex items-center gap-1.5"><Translate size={17} className="text-accent" /> English · हिन्दी · ಕನ್ನಡ</li>
              <li className="flex items-center gap-1.5"><LockKey size={17} className="text-accent" /> No voice biometrics</li>
              <li className="flex items-center gap-1.5"><SealCheck size={17} className="text-accent" /> Signed receipts</li>
            </ul>
          </div>
          <div className="motion-enter w-full" style={{ "--i": 3 } as CSSProperties}>
            <VerifyDemo />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <Reveal className="mb-6 flex flex-wrap items-end justify-between gap-2">
          <h2 className="font-display text-3xl font-semibold tracking-tight">Live from this verifier</h2>
          <p className="text-sm text-ink-soft">Real counts from the database, refreshed on load. Nothing here is made up.</p>
        </Reveal>
        <LiveNumbers />
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <Reveal>
          <h2 className="font-display text-3xl font-semibold tracking-tight md:text-5xl">Four steps, under a minute.</h2>
          <p className="mt-3 max-w-[60ch] text-ink-soft">
            Each risky Request gets live Challenges a recording cannot answer and a clone struggles with. Low-risk Requests
            pass straight through.
          </p>
        </Reveal>
        <Reveal className="relative mt-10">
          <div className="draw absolute left-0 right-0 top-6 hidden h-px bg-gradient-to-r from-accent via-accent/50 to-transparent md:block" aria-hidden />
          <ol className="grid gap-8 md:grid-cols-4">
            {HOW.map(([Glyph, title, body], k) => (
              <li key={title} className="relative flex flex-col gap-3">
                <span className="relative z-10 grid size-12 place-items-center rounded-xl border border-line bg-surface text-accent">
                  <Glyph size={24} />
                </span>
                <span className="font-mono text-xs text-ink-soft">0{k + 1}</span>
                <h3 className="text-lg font-semibold">{title}</h3>
                <p className="text-sm leading-relaxed text-ink-soft">{body}</p>
              </li>
            ))}
          </ol>
        </Reveal>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <Reveal className="mb-8">
          <h2 className="font-display text-3xl font-semibold tracking-tight md:text-5xl">Defence in depth.</h2>
        </Reveal>
        <div className="grid auto-rows-[minmax(10rem,auto)] gap-4 md:grid-cols-4">
          {DEFENCES.map(([Glyph, title, body, span], k) => (
            <Reveal key={title} i={k} className={`lift flex flex-col gap-3 rounded-2xl border border-line bg-surface p-6 ${span}`}>
              <Glyph size={k === 0 ? 34 : 26} className="text-accent" />
              <h3 className={`font-semibold ${k === 0 ? "font-display text-2xl tracking-tight" : "text-base"}`}>{title}</h3>
              <p className={`leading-relaxed text-ink-soft ${k === 0 ? "max-w-[46ch]" : "text-sm"}`}>{body}</p>
              {k === 0 && (
                <div className="mt-auto flex flex-wrap items-center gap-2 pt-4 font-mono text-xs">
                  {["Caller", "Interpreter", "Policy", "Verdict"].map((s, n) => (
                    <span key={s} className="flex items-center gap-2">
                      <span className={`rounded-full px-2.5 py-1 ring-1 ${s === "Policy" ? "bg-accent/12 text-accent ring-accent/30" : "ring-line"}`}>{s}</span>
                      {n < 3 && <ArrowRight size={13} className="text-ink-soft" />}
                    </span>
                  ))}
                </div>
              )}
            </Reveal>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <Reveal className="mb-6">
          <h2 className="font-display text-3xl font-semibold tracking-tight">See it working</h2>
        </Reveal>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PLACES.map(([Glyph, to, title, body], k) => (
            <Reveal key={to} i={k}>
              <Link to={to} className="lift group flex h-full flex-col gap-2 rounded-2xl border border-line bg-surface p-5 hover:border-accent/40">
                <span className="flex items-center justify-between">
                  <Glyph size={24} className="text-accent" />
                  <ArrowUpRight size={18} className="nudge text-ink-soft group-hover:text-accent" />
                </span>
                <span className="mt-2 font-semibold">{title}</span>
                <span className="text-sm text-ink-soft">{body}</span>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-8 text-sm text-ink-soft">
          <Logo size={24} />
          <span>
            <b className="font-display text-ink">प्रत्यक्ष</b> · perceived directly, with one's own senses.
          </span>
          <span className="ml-auto">Team Omnitrons · FET Aavishkar 2026</span>
        </div>
      </footer>
    </div>
  );
}
