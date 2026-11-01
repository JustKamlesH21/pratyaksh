/* The landing page: for judges and bank decision-makers. Dark by default, one accent (bank navy), Verdict
   colours only for Verdicts. Every product picture is a real component preview (LandingParts.tsx), every
   figure is either live from this verifier, measured by us, read from policy.yaml, or cited with its source.
   Motion is CSS only (index.css, "Landing page" block), driven by IntersectionObserver, and off under
   prefers-reduced-motion. Radii: landing cards rounded-2xl; buttons (.btn), chips and badges are pills.
   Each section opens straight on its claim: the headings read in order as one argument. */
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, ArrowUpRight, Broadcast, ChatsCircle, Check, DeviceMobile, Gavel, HardDrives, type Icon, LinkSimple,
  LockSimple,
  Plugs, Scales, SealCheck, Siren, Waveform,
} from "@phosphor-icons/react";
import { api } from "../api";
import { LiveNumber, Logo, Reveal, VerdictBadge } from "../components";
import type { EvalRun, Stats } from "../types";
import {
  AgentLine, CallerLine, PossessionCodePreview, Source, useInView,
} from "./LandingParts";
import { HeroReel } from "./LandingHero";

const H2 = "font-display text-3xl font-semibold leading-[1.08] tracking-[-0.02em] md:text-5xl";

/* ------------------------------------------------------------------ calls to action */

function PrimaryCta() {
  return (
    <Link to="/demo" className="btn btn-primary btn-lg">
      Open the demo
    </Link>
  );
}

function ConsoleCta() {
  return (
    <Link to="/console" className="btn btn-quiet btn-lg">
      Open the Console
    </Link>
  );
}

/* ------------------------------------------------------------------ hero */

function Hero() {
  return (
    <section className="relative">
      <div className="lp-halo pointer-events-none absolute inset-0" aria-hidden />
      <div className="lp-field pointer-events-none absolute inset-0" aria-hidden />
      <div className="relative mx-auto grid min-h-[min(calc(100dvh-4rem),56rem)] max-w-7xl items-center gap-12 px-4 py-12 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:py-10">
        <div className="flex flex-col items-start gap-7">
          <h1 className="motion-enter font-display text-[2.75rem] font-semibold leading-[1.04] tracking-[-0.025em] sm:text-6xl">
            Verify the person,
            <span className="block">
              not the{" "}
              <span className="relative inline-block pb-1">
                voice.
                <svg className="lp-underline absolute -bottom-1 left-0 h-3 w-[92%] text-brand-red" viewBox="0 0 120 12" preserveAspectRatio="none" aria-hidden>
                  <path d={WAVE_PATH} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                </svg>
              </span>
            </span>
          </h1>
          <p className="motion-enter max-w-[34ch] text-xl leading-snug text-ink-soft" style={{ "--i": 2 } as CSSProperties}>
            A cloned voice can fool your ear. It can’t hold your phone.
          </p>
          <div className="motion-enter flex flex-wrap gap-3" style={{ "--i": 3 } as CSSProperties}>
            <PrimaryCta />
            <ConsoleCta />
          </div>
          <p className="motion-enter flex flex-wrap items-center gap-2 text-sm text-ink-soft" style={{ "--i": 4 } as CSSProperties}>
            <span className="w-full sm:w-auto">Call verification for banks, in</span>
            {[["English", undefined], ["हिन्दी", "hi"], ["ಕನ್ನಡ", "kn"]].map(([w, l]) => (
              <span key={w} lang={l} className="rounded-full bg-sunken px-3 py-1 font-medium text-ink ring-1 ring-line">{w}</span>
            ))}
          </p>
        </div>
        <HeroReel />
      </div>
    </section>
  );
}

/** A short voice wave for the red stroke under "voice" (viewBox 120 x 12). */
const WAVE_PATH = Array.from({ length: 8 }, (_, i) => `${i === 0 ? "M0 6 " : ""}Q ${i * 15 + 7.5} ${i % 2 ? 11 : 1} ${i * 15 + 15} 6`).join(" ");

/* ------------------------------------------------------------------ the threat (cited) */

function Threat() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-20 md:py-28">
      <Reveal>
        <h2 className={`${H2} max-w-[20ch]`}>Cloned voices already fool people, and bank voice ID.</h2>
      </Reveal>
      <div className="mt-12 grid gap-12 md:grid-cols-[1.35fr_1fr] md:gap-16">
        <Reveal className="flex flex-col gap-4">
          <span className="h-1 w-14 rounded-full bg-brand-red" aria-hidden />
          <p className="font-display text-5xl font-medium tracking-[-0.035em] sm:text-6xl md:text-8xl">
            ₹22,846<span className="text-3xl text-ink-soft md:text-4xl"> crore</span>
          </p>
          <p className="max-w-[40ch] text-lg leading-relaxed text-ink-soft">
            lost by Indians to cyber fraud in 2024, about three times the year before.
          </p>
          <Source href="https://www.theweek.in/wire-updates/business/2025/07/22/del23-lsq-cyber-fraud.html">
            MHA reply in Parliament, I4C data, July 2025 (PTI)
          </Source>
        </Reveal>
        <div className="flex flex-col gap-10 md:pt-4">
          <Reveal i={1} className="flex flex-col gap-2">
            <p className="font-display text-5xl font-medium tracking-[-0.03em]">69%</p>
            <p className="text-ink-soft">of Indian adults could not tell a cloned voice from a real one.</p>
          </Reveal>
          <Reveal i={2} className="flex flex-col gap-2">
            <p className="font-display text-5xl font-medium tracking-[-0.03em]">47%</p>
            <p className="text-ink-soft">had faced an AI voice scam, or knew someone who had.</p>
            <Source href="https://businessworld.in/article/ai-voice-scams-more-prevalent-in-india-affects-almost-50-indians-mcafee-report-475192">
              McAfee survey, 2023 (BusinessWorld)
            </Source>
          </Reveal>
        </div>
      </div>
      <Reveal className="mt-14 flex max-w-[68ch] flex-col gap-2 border-l-2 border-accent pl-5">
        <p className="leading-relaxed">
          In 2023 a journalist got into his own Lloyds Bank account by playing an AI clone of his voice to its Voice ID.
          The usual fallback, an OTP read out on the call, is what scam scripts talk victims into sharing.
        </p>
        <Source href="https://www.itbrew.com/stories/2023/03/31/voice-generation-ai-blows-through-bank-s-voice-id-security">
          IT Brew, March 2023
        </Source>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------------ how a Call is checked */

interface FlowStep {
  name: string;
  icon: Icon;
  at: string; // when it happens on a typical Call
  who: string; // who acts at this step
  body: string;
  preview: (seen: boolean) => ReactNode;
}

const FLOW: FlowStep[] = [
  {
    name: "Request",
    icon: ChatsCircle,
    at: "0:00",
    who: "Caller speaks",
    body: "The Voice Agent works out what the Caller wants, in English, Hindi or Kannada. The Policy picks the Challenges.",
    preview: () => <RequestPreview />,
  },
  {
    name: "Whisper Phrase",
    icon: Waveform,
    at: "0:08",
    who: "Caller whispers",
    body: "A random everyday phrase in the Customer’s language, whispered back. It shows a live person is answering, right now.",
    preview: () => <WhisperPreview />,
  },
  {
    name: "Possession Code",
    icon: DeviceMobile,
    at: "0:15",
    who: "Registered Device",
    body: "A one-time code appears only in the Bank App on the Registered Device. The Caller reads it aloud. A Clone does not hold the phone.",
    preview: () => <CodePreview />,
  },
  {
    name: "Verdict",
    icon: SealCheck,
    at: "0:22",
    who: "Policy decides",
    body: "The Policy, never the LLM, returns PASS, STEP-UP or BLOCK, with a plain-language Reason for each Signal that drove it.",
    preview: (seen) => <VerdictPreview seen={seen} />,
  },
];

function RequestPreview() {
  const rows: [string, string][] = [
    ["balance_enquiry", "none"],
    ["add_payee", "whisper_phrase, possession_code"],
    ["sim_swap", "whisper_phrase ×2, possession_code"],
  ];
  return (
    <div className="flex flex-col gap-4">
      <div className="lp-line" style={{ "--i": 0 } as CSSProperties}>
        <CallerLine who="Caller as Rahul Verma" lang="hi" text="मुझे नया payee add करना है" chips={[["हिन्दी", ""], ["Request", ""], ["Add payee", "text-accent"]]} />
      </div>
      <div className="lp-line rounded-xl bg-sunken p-3.5 text-xs" style={{ "--i": 1 } as CSSProperties}>
        <p className="text-ink-soft">Challenges per Request, from policy.yaml</p>
        <ul className="mt-2.5 flex flex-col gap-1.5 font-mono">
          {rows.map(([req, ch]) => (
            <li key={req} className={`flex flex-wrap justify-between gap-x-4 ${req === "add_payee" ? "text-accent" : "text-ink-soft"}`}>
              <span>{req}</span>
              <span>{ch}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function WhisperPreview() {
  return (
    <div className="flex flex-col gap-4">
      <div className="lp-line" style={{ "--i": 0 } as CSSProperties}>
        <AgentLine lang="hi">Please whisper these words. कल सात बजे meeting है.</AgentLine>
      </div>
      <div className="lp-line" style={{ "--i": 1 } as CSSProperties}>
        <CallerLine who="A real whisper, on an iPhone" lang="hi" text="कल सात बजे meeting है" chips={[["task 1.00", ""], ["whisper 1.00", "text-pass"]]} />
      </div>
      <div className="lp-line" style={{ "--i": 2 } as CSSProperties}>
        <CallerLine who="A text-to-speech Caller" lang="hi" text="कल सात बजे meeting है" chips={[["task 0.92", ""], ["whisper 0.25", "text-block"]]} />
      </div>
      <p className="lp-line text-xs leading-relaxed text-ink-soft" style={{ "--i": 3 } as CSSProperties}>
        Measured on our first real and synthetic Calls. The synthetic Caller said the right words but scored 0.01 to 0.25 on whispering. The Policy
        needs 0.60.
      </p>
    </div>
  );
}

function CodePreview() {
  return (
    <div className="flex flex-col gap-4">
      <div className="lp-line" style={{ "--i": 0 } as CSSProperties}>
        <PossessionCodePreview code="481927" request="Add payee" />
      </div>
      <div className="lp-line" style={{ "--i": 3 } as CSSProperties}>
        <CallerLine who="Caller" text="four eight one nine two seven" chips={[["code matches", "text-pass"]]} />
      </div>
    </div>
  );
}

function VerdictPreview({ seen }: { seen: boolean }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="lp-line rounded-xl border border-line bg-canvas/60 p-4" style={{ "--i": 0 } as CSSProperties}>
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-ink-soft">Rahul, holding his phone</span>
          {seen && <VerdictBadge verdict="PASS" large />}
        </div>
        <p className="mt-2 text-sm leading-relaxed">
          Liveness at or above the Policy’s 0.75. A signed Verification Receipt lets core banking act, once.
        </p>
      </div>
      <div className="lp-line rounded-xl border border-line bg-canvas/60 p-4" style={{ "--i": 2 } as CSSProperties}>
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-ink-soft">The synthetic Caller</span>
          {seen && <VerdictBadge verdict="BLOCK" large />}
        </div>
        <p className="mt-2 font-mono text-xs leading-relaxed">
          Challenge 1 (Whisper Phrase): phrase was not whispered (whisper score 0.25, needs 0.60).
        </p>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Security Alert on the Registered Device. Voice Pause for 30 minutes or until the Customer dismisses it.
        </p>
      </div>
    </div>
  );
}

/** One step of the Call: a big numeral that fills in while this step is the one being read, when it happens
 *  on the Call and who acts, then the real screen for that step. */
function FlowStepCard({ step, k, active, setRef }: {
  step: FlowStep;
  k: number;
  active: boolean;
  setRef: (el: HTMLLIElement | null) => void;
}) {
  const [ref, seen] = useInView<HTMLDivElement>();
  const Glyph = step.icon;
  return (
    <li ref={setRef} data-step={k} className="flex w-[86%] shrink-0 snap-start scroll-mt-24 lg:w-auto">
      <div
        ref={ref}
        className={`reveal ${seen ? "is-visible" : ""} grid w-full content-start gap-8 rounded-2xl border bg-surface p-6 md:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] md:p-8 ${
          active ? "elev-2 border-accent/40" : "elev-1 border-line"
        }`}
      >
        <div className="flex flex-col gap-4">
          <div className="flex items-end justify-between gap-4">
            <span className={`lp-numeral ${active ? "is-on" : ""} font-display text-7xl font-semibold leading-none tracking-[-0.04em]`} aria-hidden>
              0{k + 1}
            </span>
            <span className="mb-1.5 rounded-full bg-sunken px-3 py-1 font-mono text-xs text-ink-soft ring-1 ring-line">{step.at}</span>
          </div>
          <div>
            <h3 className="font-display text-3xl font-semibold tracking-[-0.02em]">{step.name}</h3>
            <p className="mt-1 flex items-center gap-1.5 text-sm font-medium text-ink-soft">
              <Glyph size={16} className="text-accent" aria-hidden /> {step.who}
            </p>
          </div>
          <p className="leading-relaxed text-ink-soft">{step.body}</p>
        </div>
        <div>{step.preview(seen)}</div>
      </div>
    </li>
  );
}

/** The four steps of a Call. The step nearest the middle of the screen is "active": the index on the
 *  left follows it and its rail fills, so the reader always knows where they are in the Call. Below 64rem
 *  the steps are a row to swipe (four stacked steps ran to four phone screens), so the middle is sideways. */
function CallFlow() {
  const [active, setActive] = useState(0);
  const items = useRef<(HTMLLIElement | null)[]>([]);
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const wide = matchMedia("(min-width: 64rem)").matches;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.step));
      },
      { rootMargin: wide ? "-45% 0px -50% 0px" : "0px -45% 0px -45%" },
    );
    items.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);
  return (
    <section className="border-y border-line bg-surface/40">
      <div className="mx-auto grid max-w-7xl grid-cols-[minmax(0,1fr)] gap-12 px-4 py-20 md:py-28 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:gap-16">
        <div className="lg:sticky lg:top-24 lg:self-start">
          <Reveal>
            <h2 className={H2}>How a Call is checked</h2>
            <p className="mt-4 max-w-[40ch] leading-relaxed text-ink-soft">
              Balance enquiries go straight through. Adding a payee, a SIM swap or a big transfer gets live
              Challenges first.
            </p>
          </Reveal>
          <ol className="relative mt-10 hidden flex-col gap-5 lg:flex" aria-hidden>
            {/* the Call’s timeline: a red thread that fills as you read, like a recording’s progress */}
            <span className="absolute bottom-2 left-[5px] top-2 w-0.5 rounded-full bg-line" />
            <span
              className="lp-rail-fill absolute bottom-2 left-[5px] top-2 w-0.5 rounded-full bg-brand-red"
              style={{ "--p": active / (FLOW.length - 1) } as CSSProperties}
            />
            {FLOW.map((s, k) => (
              <li key={s.name} className="relative flex items-center gap-4">
                <span className={`lp-mark size-3 rounded-full ring-4 ring-canvas ${k <= active ? "bg-brand-red" : "bg-line-strong"}`} />
                <span className="w-10 font-mono text-xs text-ink-soft">{s.at}</span>
                <span className={`lp-mark text-sm font-medium ${k === active ? "text-ink" : "text-ink-soft"}`}>{s.name}</span>
              </li>
            ))}
          </ol>
        </div>
        <ol
          tabIndex={0}
          aria-label="The four steps of a Call"
          className="-mx-4 flex snap-x snap-mandatory scroll-px-4 gap-4 overflow-x-auto overscroll-x-contain px-4 pb-2 lg:mx-0 lg:snap-none lg:flex-col lg:gap-6 lg:overflow-visible lg:px-0 lg:pb-0"
        >
          {FLOW.map((s, k) => (
            <FlowStepCard key={s.name} step={s} k={k} active={k === active} setRef={(el) => {
                items.current[k] = el;
              }} />
          ))}
        </ol>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ the honest limit */

function WhatEachProves() {
  return (
    // The bank’s navy band: the one claim the whole design rests on, said plainly, with the red under it.
    <section className="relative overflow-hidden bg-brand text-on-fill">
      <div className="pointer-events-none absolute -right-24 top-1/2 -translate-y-1/2 opacity-[0.07]" aria-hidden>
        <Logo size={560} />
      </div>
      <div className="relative mx-auto max-w-7xl px-4 py-20 md:py-28">
        <Reveal>
          <h2 className="max-w-[22ch] font-display text-3xl font-semibold leading-[1.12] tracking-[-0.02em] md:text-6xl">
            The whisper proves a live person.{" "}
            <span>
              The code proves it is the Customer.
            </span>
          </h2>
          <span className="mt-6 block h-1 w-24 rounded-full bg-brand-red" aria-hidden />
        </Reveal>
        <div className="mt-12 grid gap-10 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)]">
          <Reveal i={1} className="flex flex-col gap-3">
            <span className="grid size-11 place-items-center rounded-full bg-on-fill/12"><Waveform size={22} /></span>
            <p className="font-semibold">Whisper Phrase</p>
            <p className="text-sm leading-relaxed text-on-fill/80">Someone is on the line right now, saying words they could not have recorded in advance.</p>
          </Reveal>
          <Reveal i={2} className="flex flex-col gap-3">
            <span className="grid size-11 place-items-center rounded-full bg-on-fill/12"><DeviceMobile size={22} /></span>
            <p className="font-semibold">Possession Code</p>
            <p className="text-sm leading-relaxed text-on-fill/80">That someone holds the Customer’s Registered Device. A cloned voice cannot.</p>
          </Reveal>
          <Reveal i={3} className="rounded-2xl bg-on-fill/8 p-6 ring-1 ring-on-fill/15">
            <h3 className="font-semibold">The honest limit</h3>
            <p className="mt-2 text-sm leading-relaxed text-on-fill/85">
              We attacked our own Whisper Score: text-to-speech run through a whisper filter passed it 30 times out of
              30. So no single Signal decides. Every risky Request also needs the Possession Code, and the spoof model
              only advises.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ around every Verdict */

const CHIP = "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-xs";

const DEFENCES: { icon: Icon; title: string; body: string; cls: string; visual?: ReactNode }[] = [
  {
    icon: Gavel,
    title: "The LLM never decides",
    body: "Keyword rules and an LLM work out what the Caller means. Only the Policy sets a Verdict. LLM replies with numbers, outcome claims or asks for a code are dropped before they are spoken.",
    cls: "lp-tint md:col-span-2 md:row-span-2",
  },
  {
    icon: Siren,
    title: "Security Alert and Voice Pause",
    body: "Every BLOCK alerts the Registered Device. Risky voice Requests stay paused until the Customer dismisses it.",
    cls: "bg-surface md:col-span-2",
    visual: (
      <div className="flex flex-wrap gap-2">
        <span className={`${CHIP} bg-block/10 font-sans font-semibold text-block`}><Siren size={14} weight="fill" aria-hidden /> Blocked call attempt</span>
        <span className={`${CHIP} bg-sunken text-ink-soft ring-1 ring-line`}><LockSimple size={13} weight="fill" aria-hidden /> Voice Pause · 30 min</span>
      </div>
    ),
  },
  {
    icon: Broadcast,
    title: "Attack Wave",
    body: "Blocked Calls for 3 Customers within 15 minutes put Agent Review on every risky Request.",
    cls: "bg-sunken md:col-span-2",
    visual: (
      <div className="flex items-center gap-3">
        <span className="flex -space-x-2" aria-hidden>
          {["AN", "MS", "RV"].map((n) => (
            <span key={n} className="grid size-9 place-items-center rounded-full bg-surface text-xs font-semibold ring-2 ring-block">{n}</span>
          ))}
        </span>
        <span className="text-xs text-ink-soft">3 of 3 Customers in 15 min, then Agent Review</span>
      </div>
    ),
  },
  {
    icon: LinkSimple,
    title: "Insert-only Audit Trail",
    body: "Each event is hash-chained to the one before. Edit or remove one and the Console shows where.",
    cls: "lp-dots md:col-span-2",
    visual: (
      <div className="flex flex-wrap items-center gap-1.5" aria-hidden>
        {["#41 a3f9", "#42 7c21", "#43 e04b"].map((h, n) => (
          <span key={h} className="flex items-center gap-1.5">
            <span className={`${CHIP} bg-surface text-ink ring-1 ring-line`}>{h}</span>
            {n < 2 && <LinkSimple size={13} className="text-brand-red" />}
          </span>
        ))}
      </div>
    ),
  },
  {
    icon: SealCheck,
    title: "Signed Verification Receipts",
    body: "Ed25519-signed, a standard JWT. Core banking checks it and redeems it once before acting.",
    cls: "bg-surface md:col-span-2",
    visual: (
      <div className="flex flex-wrap items-center gap-2" aria-hidden>
        <span className={`${CHIP} max-w-[14rem] truncate bg-sunken text-ink-soft ring-1 ring-line`}>eyJhbGciOiJFZERTQSJ9.eyJzdWIi…</span>
        <span className={`${CHIP} bg-accent/12 font-sans font-semibold text-accent`}><Check size={13} weight="bold" /> redeemed once</span>
      </div>
    ),
  },
];

function Defences() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-20 md:py-28">
      <Reveal className="mb-10">
        <h2 className={H2}>Safeguards around every Verdict</h2>
      </Reveal>
      <div className="grid gap-4 md:grid-cols-4">
        {DEFENCES.map(({ icon: Glyph, title, body, cls, visual }, k) => (
          <Reveal key={title} i={k} className={`lift flex flex-col gap-3 rounded-2xl border border-line p-6 ${cls}`}>
            {visual && <div className="order-last mt-auto pt-3">{visual}</div>}
            <Glyph size={k === 0 ? 34 : 26} className="text-accent" />
            <h3 className={k === 0 ? "font-display text-2xl font-semibold tracking-tight" : "font-semibold"}>{title}</h3>
            <p className={`leading-relaxed text-ink-soft ${k === 0 ? "max-w-[44ch]" : "text-sm"}`}>{body}</p>
            {k === 0 && (
              <div className="mt-auto flex flex-wrap items-center gap-2 pt-6 text-xs font-medium">
                {["Caller", "Interpreter", "Policy", "Verdict"].map((s, n) => (
                  <span key={s} className="flex items-center gap-2">
                    <span className={`rounded-full px-2.5 py-1 ring-1 ${s === "Policy" ? "bg-accent/12 text-accent ring-accent/30" : "bg-surface ring-line"}`}>{s}</span>
                    {n < 3 && <ArrowRight size={13} className="text-ink-soft" />}
                  </span>
                ))}
              </div>
            )}
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ live and measured */

type LiveState = "loading" | "live" | "offline";

function LiveNumbers({ onState }: { onState: (s: LiveState) => void }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    api
      .stats()
      .then((s) => {
        setStats(s);
        onState("live");
      })
      .catch(() => {
        setOffline(true);
        onState("offline");
      });
    api.latestEval().then(setRun).catch(() => undefined);
  }, [onState]);
  if (offline)
    return (
      <div className="flex items-start gap-4 rounded-2xl border border-dashed border-line p-6">
        <Plugs size={26} className="mt-0.5 shrink-0 text-ink-soft" />
        <div>
          <p className="font-semibold">The verifier is not running on this machine.</p>
          <p className="mt-1 text-sm leading-relaxed text-ink-soft">
            Start it with <code className="font-mono">scripts\windows\start.ps1</code> and reload: Calls, blocks,
            Added Time and hearing times appear here, counted from its database.
          </p>
        </div>
      </div>
    );
  if (!stats)
    return (
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4" aria-busy="true">
        {[0, 1, 2, 3].map((k) => <div key={k} className="skeleton h-28" />)}
      </div>
    );
  const tiles: [string, number | null, number, string, string][] = [
    ["Calls verified", stats.calls, 0, "", "on this verifier"],
    ["Calls blocked", stats.blocked, 0, "", "Clones and failed checks"],
    ["Added Time", stats.avg_added_seconds, 1, " s", "for genuine Callers"],
    ["Hearing a Response", stats.hearing_ms.p50, 0, " ms", "median, speech models and understanding"],
  ];
  if (run?.summary.catch_rate != null)
    tiles.push(["Catch Rate", run.summary.catch_rate * 100, 0, "%", `latest Eval Run, ${run.summary.clone_calls} Clone Calls`]);
  if (run?.summary.false_reject_rate != null)
    tiles.push(["False Reject Rate", run.summary.false_reject_rate * 100, 0, "%", `latest Eval Run, ${run.summary.real_calls} real Calls`]);
  return (
    <div className="flex flex-col gap-4">
      <div className={`grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line ${tiles.length > 4 ? "md:grid-cols-3" : "md:grid-cols-4"}`}>
        {tiles.map(([label, value, decimals, unit, hint], k) => (
          <Reveal key={label} i={k} className="flex flex-col gap-1 bg-surface p-5">
            <span className="text-xs font-medium text-ink-soft">{label}</span>
            <span className="font-display text-3xl font-medium tracking-[-0.03em] md:text-4xl">
              {value === null ? "-" : <LiveNumber value={value} decimals={decimals} />}
              {value !== null && <span className="text-xl text-ink-soft">{unit}</span>}
            </span>
            <span className="text-xs text-ink-soft">{hint}</span>
          </Reveal>
        ))}
      </div>
      {stats.calls === 0 && (
        <p className="text-sm text-ink-soft">
          No Calls on this verifier yet.{" "}
          <Link to="/call" className="font-medium text-accent underline-offset-4 hover:underline">Place a test call</Link> and it is
          counted here.
        </p>
      )}
    </div>
  );
}

const MEASURED: [string, string][] = [
  ["0.53 to 0.74 s", "to hear a Caller’s Response, on smoke Calls with every prompt pre-voiced"],
  ["75 to 95 s", "from a cold start to Ready, with every model loaded offline"],
  ["7 to 19 ms", "to serve a pre-voiced Voice Agent line"],
];

function Live() {
  const [state, setState] = useState<LiveState>("loading");
  return (
    <section className="border-t border-line">
      <div className="mx-auto grid max-w-7xl gap-12 px-4 py-20 md:py-28 lg:grid-cols-[minmax(0,1fr)_19rem] lg:gap-14">
        <div>
          <Reveal className="mb-8 flex flex-wrap items-center gap-x-4 gap-y-2">
            <h2 className={H2}>Live from this verifier</h2>
            {state === "live" && (
              <span className="inline-flex items-center gap-2 rounded-full bg-accent/12 px-3 py-1 text-xs font-semibold text-accent">
                <span className="live-dot" aria-hidden /> Connected
              </span>
            )}
          </Reveal>
          <LiveNumbers onState={setState} />
        </div>
        <Reveal i={1} className="flex flex-col gap-6 lg:border-l lg:border-line lg:pl-10">
          <h3 className="font-semibold">Measured on our GPU laptop, Oct 27</h3>
          {MEASURED.map(([value, what]) => (
            <div key={value} className="flex flex-col gap-1">
              <p className="font-display text-3xl font-medium tracking-[-0.03em]">{value}</p>
              <p className="text-sm leading-relaxed text-ink-soft">{what}</p>
            </div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ why a bank can adopt it */

const RULES: { title: string; body: string; source: [string, string] }[] = [
  {
    title: "RBI Digital Payment Authentication Directions, Sep 2025",
    body: "At least two factors plus risk-based checks, due by 1 April 2026. A Possession Code with a live Challenge is that kind of check.",
    source: ["RBI press release", "https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=61282"],
  },
  {
    title: "RBI circular on voice-call and SMS fraud, Jan 2025",
    body: "A registered mobile number changes only after due verification. SIM swaps and number changes are where Pratyaksh sits.",
    source: ["MediaNama", "https://www.medianama.com/2025/01/223-rbi-transactional-calls-financial-fraud/"],
  },
  {
    title: "DPDP Rules, notified Nov 2025",
    body: "Penalties up to ₹250 crore for weak security safeguards. Pratyaksh enrols and stores no voiceprint, so there is none to leak.",
    source: ["PIB", "https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf"],
  },
];

const DEPLOY: [string, string][] = [
  ["On the bank’s own servers", "Designed to run on-premises or in the bank’s own cloud. Response audio is scored in memory and discarded."],
  ["Works offline", "Speech models, the Voice Agent’s voice and the web app load locally. Without internet, understanding falls back to keyword rules."],
  ["Joins the existing phone line", "Today Calls arrive over WebRTC through a self-hosted LiveKit server. A bank would add a SIP trunk from its telephony; Verification does not change."],
  ["Core banking stays in charge", "It acts only on a valid, unredeemed Verification Receipt, which any bank system can check with a standard JWT library."],
];

function Adoption() {
  return (
    <section className="border-t border-line bg-surface/40">
      <div className="mx-auto max-w-7xl px-4 py-20 md:py-28">
        <Reveal>
          <h2 className={`${H2} max-w-[22ch]`}>Why a bank can adopt it</h2>
        </Reveal>
        <div className="mt-14 grid gap-14 md:grid-cols-2 md:gap-16">
          <Reveal className="flex flex-col gap-8">
            <h3 className="flex items-center gap-2.5 font-semibold"><Scales size={22} className="text-accent" /> Regulation</h3>
            {RULES.map(({ title, body, source: [label, href] }) => (
              <div key={title} className="flex flex-col gap-1.5">
                <p className="font-medium">{title}</p>
                <p className="text-sm leading-relaxed text-ink-soft">{body}</p>
                <Source href={href}>{label}</Source>
              </div>
            ))}
          </Reveal>
          <Reveal i={1} className="flex flex-col gap-8">
            <h3 className="flex items-center gap-2.5 font-semibold"><HardDrives size={22} className="text-accent" /> Deployment</h3>
            {DEPLOY.map(([title, body]) => (
              <div key={title} className="flex flex-col gap-1.5">
                <p className="font-medium">{title}</p>
                <p className="text-sm leading-relaxed text-ink-soft">{body}</p>
              </div>
            ))}
          </Reveal>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ call to action and footer */

const MORE: [string, string][] = [
  ["/call", "Place a test call"],
  ["/bank", "Bank App"],
  ["/eval", "Eval Runs"],
];

function FinalCta() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-20 md:py-28">
      <Reveal className="relative overflow-hidden rounded-[2rem] bg-brand p-8 text-on-fill md:p-14">
        <div className="pointer-events-none absolute -bottom-40 -right-28 opacity-[0.08]" aria-hidden>
          <Logo size={420} />
        </div>
        <div className="relative grid gap-8 md:grid-cols-[minmax(0,1.4fr)_auto] md:items-end">
          <div>
            <span className="mb-6 block h-1 w-14 rounded-full bg-brand-red" aria-hidden />
            <h2 className={H2}>Follow a Call from Request to Verdict.</h2>
            <p className="mt-4 max-w-[52ch] leading-relaxed text-on-fill/80">
              Open the demo to see Pratyaksh at work, or the Console for live Calls with their Signals, Verdicts and
              Transcripts.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 md:justify-end">
            <Link to="/demo" className="btn btn-on-brand btn-lg">
              Open the demo
            </Link>
            <Link to="/console" className="btn btn-outline-on-brand btn-lg">Open the Console</Link>
          </div>
        </div>
        <nav className="relative mt-10 flex flex-wrap gap-x-8 gap-y-3 border-t border-on-fill/15 pt-6 text-sm" aria-label="More of Pratyaksh">
          {MORE.map(([to, label]) => (
            <Link key={to} to={to} className="group inline-flex items-center gap-1.5 font-medium text-on-fill/80 hover:text-on-fill">
              {label} <ArrowUpRight size={15} className="nudge group-hover:text-brand-red" />
            </Link>
          ))}
        </nav>
      </Reveal>
    </section>
  );
}

export default function LandingPage() {
  return (
    <div className="overflow-x-clip">
      <Hero />
      <Threat />
      <CallFlow />
      <WhatEachProves />
      <Defences />
      <Live />
      <Adoption />
      <FinalCta />
      <footer className="border-t border-line bg-surface/40">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
          <div className="flex flex-col gap-4">
            <Logo size={36} />
            <p className="max-w-[36ch] font-display text-2xl font-medium leading-snug tracking-[-0.015em]">
              <b lang="hi" className="font-semibold">प्रत्यक्ष</b>: perceived directly, with one’s own senses.
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Pratyaksh pages">
            {[["/demo", "Demo"], ["/deepfake", "Deepfake"], ["/console", "Console"], ...MORE].map(([to, label]) => (
              <Link key={to} to={to} className="font-medium text-ink-soft hover:text-ink">{label}</Link>
            ))}
          </nav>
        </div>
        <div className="border-t border-line">
          <p className="mx-auto max-w-7xl px-4 py-5 text-sm text-ink-soft">Team Omnitrons, FET Aavishkar 2026</p>
        </div>
      </footer>
    </div>
  );
}
