/* The live style guide (/design): every token, type sample, state, component and animation of the web app,
   rendered from the same CSS and components the product uses, so it cannot drift from them. The written
   version is docs/DESIGN.md. Sample Calls on this page are labelled as samples; nothing here is live data. */
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";
import {
  ArrowCounterClockwise, Bank, Check, CircleNotch, LockSimple, Microphone, MicrophoneSlash, PhoneCall,
  PhoneDisconnect, Play, ShieldCheck, User,
} from "@phosphor-icons/react";
import { Meter, VerdictBadge, prefersReducedMotion } from "../components";
import type { CallView, DeviceMessage, Signals } from "../types";
import { PossessionCode } from "./BankAppPage";
import { VerdictRibbon } from "./DemoPage";
import { DeviceFrame, SecurityAlertPreview } from "./LandingParts";

/* ------------------------------------------------------------------ colour maths (WCAG 2.x) */

/** Linear sRGB from an "oklch(L C H)" string, clipped to the sRGB gamut. */
function oklchToLinear(value: string): [number, number, number] | null {
  const m = /oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)/.exec(value);
  if (!m) return null;
  const L = m[2] ? Number(m[1]) / 100 : Number(m[1]);
  const C = Number(m[3]);
  const H = (Number(m[4]) * Math.PI) / 180;
  const a = C * Math.cos(H);
  const b = C * Math.sin(H);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const mm = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [
    4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * mm + 1.707614701 * s,
  ].map((v) => Math.min(1, Math.max(0, v)));
  return rgb as [number, number, number];
}
const gamma = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const toHex = (rgb: number[]) => "#" + rgb.map((v) => Math.round(gamma(v) * 255).toString(16).padStart(2, "0")).join("");
const luminance = ([r, g, b]: number[]) => 0.2126 * r + 0.7152 * g + 0.0722 * b;
function contrast(a: number[], b: number[]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Current token values (they change with the theme), read from the page's own CSS. */
function useTokens(names: string[]): Record<string, string> {
  const read = () =>
    Object.fromEntries(names.map((n) => [n, getComputedStyle(document.documentElement).getPropertyValue(`--color-${n}`).trim()]));
  const [values, setValues] = useState(read);
  useEffect(() => {
    const update = () => setValues(read());
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", update);
    return () => {
      mo.disconnect();
      mq.removeEventListener("change", update);
    };
  }, []);
  return values;
}

/* ------------------------------------------------------------------ page */

const SECTIONS: [string, string][] = [
  ["colour", "Colour"],
  ["type", "Type"],
  ["states", "Verdict and turn states"],
  ["controls", "Controls"],
  ["phone", "Phone frame"],
  ["ribbon", "Verdict Ribbon"],
  ["motion", "Motion"],
];

export default function DesignPage() {
  return (
    <div className="flex flex-col gap-14 pb-16">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl">
          <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">Design system</h1>
          <p className="mt-2 text-ink-soft">
            The tokens, type, states, components and motion of Pratyaksh, drawn with the same CSS the product uses. The
            written version, with the rules behind each choice, is <code className="font-mono text-sm">docs/DESIGN.md</code>.
          </p>
        </div>
        <MotionToggle />
      </header>
      <nav aria-label="Sections" className="-mt-6 flex flex-wrap gap-2 text-sm">
        {SECTIONS.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="rounded-full bg-sunken px-3 py-1 font-medium text-ink-soft hover:text-ink">
            {label}
          </a>
        ))}
      </nav>
      <Colour />
      <Type />
      <States />
      <Controls />
      <Phone />
      <Ribbon />
      <MotionCatalogue />
    </div>
  );
}

function Section({ id, title, lead, children }: { id: string; title: string; lead?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20">
      <h2 className="font-display text-2xl font-semibold tracking-tight">{title}</h2>
      {lead && <p className="mt-1 max-w-[70ch] text-sm leading-relaxed text-ink-soft">{lead}</p>}
      <div className="mt-6">{children}</div>
    </section>
  );
}

/** Reduced motion without touching OS settings: html[data-motion="reduce"], remembered in this browser. */
function MotionToggle() {
  const [reduce, setReduce] = useState(() => document.documentElement.dataset.motion === "reduce");
  const os = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  function toggle() {
    const next = !reduce;
    if (next) document.documentElement.dataset.motion = "reduce";
    else delete document.documentElement.dataset.motion;
    try {
      if (next) localStorage.setItem("motion", "reduce");
      else localStorage.removeItem("motion");
    } catch {
      /* storage blocked: lasts for this page */
    }
    setReduce(next);
  }
  const on = reduce || os;
  return (
    <div className="flex flex-col items-start gap-1 lg:items-end">
      <button
        role="switch"
        aria-checked={on}
        disabled={os}
        onClick={toggle}
        className="press inline-flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ring-1 ring-line-strong disabled:opacity-60"
      >
        <span className={`relative inline-block h-5 w-9 rounded-full ${on ? "bg-accent" : "bg-sunken ring-1 ring-line-strong"}`}>
          <span className={`absolute top-0.5 size-4 rounded-full bg-surface transition-transform duration-150 ${on ? "translate-x-4.5" : "translate-x-0.5"}`} />
        </span>
        Reduce motion
      </button>
      <p className="text-xs text-ink-soft">{os ? "On in your system settings." : "Applies to every page in this browser."}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ colour */

const SURFACES = ["canvas", "surface", "sunken", "line", "line-strong", "ink", "ink-soft"];
const ACCENT = ["accent", "on-accent"];
const VERDICT = ["pass", "stepup", "block", "pass-fill", "stepup-fill", "block-fill", "on-fill"];
const ROLES = ["advisory", "turn-bank", "turn-you", "turn-wait", "bezel"];

const PAIRS: [string, string, number][] = [
  ["ink", "canvas", 4.5],
  ["ink", "surface", 4.5],
  ["ink-soft", "canvas", 4.5],
  ["ink-soft", "surface", 4.5],
  ["ink-soft", "sunken", 4.5],
  ["accent", "surface", 4.5],
  ["on-accent", "accent", 4.5],
  ["pass", "surface", 4.5],
  ["stepup", "surface", 4.5],
  ["block", "surface", 4.5],
  ["on-fill", "pass-fill", 4.5],
  ["on-fill", "stepup-fill", 4.5],
  ["on-fill", "block-fill", 4.5],
  ["line-strong", "surface", 3],
  ["accent", "canvas", 3],
];

function Colour() {
  const t = useTokens([...SURFACES, ...ACCENT, ...VERDICT, ...ROLES]);
  const rgb = (n: string) => oklchToLinear(t[n]);
  return (
    <Section
      id="colour"
      title="Colour"
      lead="One cool neutral hue, hairline borders instead of shadows, one cobalt accent for actions, focus and the bank's voice. Green, amber and red mean PASS, STEP-UP and BLOCK. Turn cues and the advisory Spoof Score have their own tokens. Values are read live from the current theme; switch the theme in the header to compare."
    >
      <div className="flex flex-col gap-8">
        <SwatchGroup title="Surfaces and ink" names={SURFACES} t={t} />
        <SwatchGroup title="Accent" names={ACCENT} t={t} />
        <SwatchGroup title="Verdict: text-safe, then solid fill" names={VERDICT} t={t} />
        <SwatchGroup title="Roles (they point at the palette)" names={ROLES} t={t} />
        <div>
          <h3 className="text-sm font-semibold">Contrast in this theme (WCAG 2.x)</h3>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {PAIRS.map(([fg, bg, need]) => {
              const a = rgb(fg);
              const b = rgb(bg);
              const r = a && b ? contrast(a, b) : null;
              return (
                <li key={fg + bg} className="flex items-center gap-3 rounded-lg border border-line bg-surface p-2.5">
                  <span
                    className="grid h-10 w-14 shrink-0 place-items-center rounded-md text-sm font-semibold"
                    style={{ background: `var(--color-${bg})`, color: `var(--color-${fg})` }}
                  >
                    Aa
                  </span>
                  <span className="min-w-0 flex-1 text-xs">
                    <code className="font-mono">{fg}</code> on <code className="font-mono">{bg}</code>
                    <span className="block text-ink-soft">{need === 3 ? "control or large text, needs 3:1" : "text, needs 4.5:1"}</span>
                  </span>
                  <span className={`font-mono text-sm font-semibold ${r !== null && r < need ? "text-block" : ""}`}>
                    {r === null ? "?" : `${r.toFixed(2)}:1`}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs text-ink-soft">
            Both themes, tinted chips included, are checked by <code className="font-mono">node web/scripts/contrast.mjs</code>.
          </p>
        </div>
      </div>
    </Section>
  );
}

function SwatchGroup({ title, names, t }: { title: string; names: string[]; t: Record<string, string> }) {
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {names.map((n) => {
          const lin = oklchToLinear(t[n]);
          return (
            <li key={n} className="overflow-hidden rounded-xl border border-line bg-surface">
              <span className="block h-16 border-b border-line" style={{ background: `var(--color-${n})` }} />
              <span className="flex flex-col gap-0.5 p-2.5 text-xs">
                <code className="font-mono font-semibold">{n}</code>
                <span className="font-mono text-[0.68rem] text-ink-soft">{t[n] || "?"}</span>
                {lin && <span className="font-mono text-[0.68rem] text-ink-soft">{toHex(lin)}</span>}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ type */

const SCALE: [string, string, string][] = [
  ["text-xs", "12", "Captions, chips, timestamps"],
  ["text-sm", "14", "Console body, labels"],
  ["text-base", "16", "UI body"],
  ["text-lg", "18", "Call captions, lead text"],
  ["text-2xl", "24", "Card titles"],
  ["text-3xl", "30", "Page titles, phase text"],
  ["text-5xl", "48", "Landing headlines"],
];

function Type() {
  return (
    <Section
      id="type"
      title="Type"
      lead="Bricolage Grotesque for display only (24 px and up, weight 600 to 700, tight tracking). Geist for UI. Geist Mono with tabular figures for scores, codes, timers, IDs and hashes. Hindi and Kannada fall through to Noto Sans with more leading, no tracking, no italics or capitals; every Indic string carries lang."
    >
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <p className="font-display font-bold leading-none tracking-[-0.03em]" style={{ fontSize: "var(--text-ribbon-compact)" }}>
            BLOCKED
          </p>
          <p className="font-mono text-xs text-ink-soft">Ribbon word: font-display 700, text-ribbon clamp(6rem, 8vw, 9rem) on stage</p>
          <p className="font-display text-phrase font-semibold leading-tight">turn left at the blue gate</p>
          <p className="font-mono text-xs text-ink-soft">Whisper Phrase: text-phrase clamp(2rem, 9vw, 2.5rem), 600</p>
          {SCALE.map(([cls, px, use]) => (
            <div key={cls} className="flex items-baseline gap-4 border-t border-line pt-2">
              <span className="w-24 shrink-0 font-mono text-xs text-ink-soft">
                {cls} {px}
              </span>
              <span className={`${cls} ${Number(px) >= 24 ? "font-display font-semibold tracking-tight" : ""} min-w-0 truncate`}>{use}</span>
            </div>
          ))}
          <p className="flex items-baseline gap-4 border-t border-line pt-2">
            <span className="w-24 shrink-0 font-mono text-xs text-ink-soft">font-mono</span>
            <span className="font-mono text-lg">482 913 · 0.62 · 1:07 · a3f9c2e1</span>
          </p>
        </div>
        <div className="flex flex-col gap-5">
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="font-mono text-xs text-ink-soft">lang="hi": line-height 1.65, headings 1.3 at 700</p>
            <h3 lang="hi" className="mt-2 font-display text-3xl font-semibold">कॉल रोकी गई</h3>
            <p lang="hi" className="mt-1">किसी ने आपके नाम से बैंक को कॉल किया। कुछ भी नहीं बदला गया। कल सात बजे meeting है।</p>
          </div>
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="font-mono text-xs text-ink-soft">lang="kn": line-height 1.75, headings 1.35 at 700</p>
            <h3 lang="kn" className="mt-2 font-display text-3xl font-semibold">ಪ್ರತ್ಯಕ್ಷ ಸ್ತ್ರೀ</h3>
            <p lang="kn" className="mt-1">ನಾಳೆ ಏಳು ಗಂಟೆಗೆ meeting ಇದೆ.</p>
          </div>
          <div className="rounded-xl border border-line bg-surface p-4 text-sm">
            <p className="font-mono text-xs text-ink-soft">An inline run inside Latin text (span[lang]) is set 10% (hi) or 5% (kn) larger</p>
            <p className="mt-2">
              The Caller said <span lang="hi">मुझे नया payee add करना है</span> and the Voice Agent heard Add payee.
            </p>
          </div>
          <p className="text-xs text-ink-soft">Indic samples are for setting type only; the Hindi and Kannada product copy is checked by a native speaker.</p>
        </div>
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------------ states */

function States() {
  return (
    <Section
      id="states"
      title="Verdict and turn states"
      lead="Every state pairs a colour with an icon shape and a word. Turn cues on the call screen never use a Verdict colour: the bank speaks in accent, your turn is ink with a solid microphone, waiting and checking are ink-soft with a spinner."
    >
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <h3 className="text-sm font-semibold">Verdict badge (tinted, text-safe colour)</h3>
          <div className="flex flex-wrap gap-2">
            <VerdictBadge verdict="PASS" large />
            <VerdictBadge verdict="STEP_UP" large />
            <VerdictBadge verdict="BLOCK" large />
            <VerdictBadge verdict={null} />
          </div>
          <h3 className="text-sm font-semibold">Verdict fill (solid, on-fill text)</h3>
          <div className="grid grid-cols-3 gap-2 text-sm font-bold">
            <span className="rounded-lg bg-pass-fill px-3 py-3 text-on-fill">PASS</span>
            <span className="rounded-lg bg-stepup-fill px-3 py-3 text-on-fill">STEP-UP</span>
            <span className="rounded-lg bg-block-fill px-3 py-3 text-on-fill">BLOCKED</span>
          </div>
          <h3 className="text-sm font-semibold">Call header status</h3>
          <div className="flex flex-wrap gap-4 text-xs">
            <span className="inline-flex items-center gap-1 font-medium text-ink-soft">
              <Bank size={13} /> Your bank · verifying you
            </span>
            <span className="inline-flex items-center gap-1 font-semibold text-pass">
              <ShieldCheck size={13} weight="fill" /> Verified call (after PASS)
            </span>
            <span className="font-semibold text-block">Not verified (after BLOCK)</span>
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <h3 className="text-sm font-semibold">Turn cues (call screen)</h3>
          <div className="grid grid-cols-3 gap-3 text-center text-sm">
            <Turn label="Bank is speaking" tone="bg-turn-bank/15 text-turn-bank ring-turn-bank/40" icon={<MicrophoneSlash size={26} />} />
            <Turn label="Your turn" tone="bg-turn-you/10 text-turn-you ring-turn-you/40" icon={<Microphone size={26} weight="fill" />} />
            <Turn label="Checking…" tone="bg-sunken text-turn-wait ring-line" icon={<CircleNotch size={26} weight="bold" className="spinner" />} />
          </div>
          <h3 className="text-sm font-semibold">Captions: a speaker chip on every line</h3>
          <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-3 text-lg">
            <p className="max-w-[85%] self-start rounded-2xl rounded-bl-md bg-sunken px-3.5 py-2.5 leading-snug">
              <span className="mb-0.5 flex items-center gap-1 text-xs font-semibold text-ink-soft">
                <Bank size={13} /> Bank
              </span>
              Please whisper these words.
            </p>
            <p className="max-w-[85%] self-end rounded-2xl rounded-br-md bg-accent/15 px-3.5 py-2.5 leading-snug ring-1 ring-accent/25">
              <span className="mb-0.5 flex items-center gap-1 text-xs font-semibold text-ink-soft">
                <User size={13} /> You
              </span>
              <span lang="hi">कल सात बजे meeting है</span>
            </p>
          </div>
        </div>
      </div>
    </Section>
  );
}

function Turn({ label, tone, icon }: { label: string; tone: string; icon: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-line bg-surface p-3">
      <span className={`grid size-14 place-items-center rounded-full ring-1 ${tone}`}>{icon}</span>
      <span className="font-medium">{label}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ controls */

function Controls() {
  return (
    <Section
      id="controls"
      title="Controls"
      lead="Controls are rounded-lg, chips and badges rounded-full, cards rounded-xl. Primary actions use the accent; approving a Request is an action, not a Verdict, so it is accent too. Control borders use line-strong (3:1)."
    >
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <button className="press inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-on-accent">
              <PhoneCall size={18} weight="bold" /> Primary
            </button>
            <button className="press rounded-lg px-4 py-2.5 text-sm font-medium text-ink-soft ring-1 ring-line hover:text-ink">Secondary</button>
            <button className="press rounded-lg bg-ink px-4 py-2.5 text-sm font-semibold text-canvas">Strong neutral</button>
            <button className="press rounded-lg bg-surface px-4 py-2.5 text-sm font-bold text-block ring-1 ring-block/40">Decline</button>
            <button disabled className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-on-accent disabled:opacity-40">
              Disabled
            </button>
          </div>
          <div className="flex items-center gap-4">
            <button className="press grid size-18 shrink-0 place-items-center rounded-full bg-block text-on-accent" aria-label="Hang up (sample)">
              <PhoneDisconnect size={32} weight="fill" />
            </button>
            <p className="text-sm text-ink-soft">Hang up: 72 px, alone in the thumb zone. The one non-Verdict use of red, a phone convention.</p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-sunken px-2.5 py-1 font-medium">Chip</span>
            <span className="rounded-full bg-accent/12 px-2.5 py-1 font-medium text-accent">Selected</span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-accent/12 px-2.5 py-1 font-medium text-accent">
              <span className="live-dot" /> Live
            </span>
            <span className="rounded-full border border-dashed border-line-strong px-2.5 py-1 text-ink-soft">Spoof Score 0.91, advisory</span>
            <span className="rounded-full bg-sunken px-2.5 py-1 font-medium">
              <span lang="hi" className="text-xs">हिन्दी</span> Hindi
            </span>
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-ink-soft">Calling as</span>
            <select className="min-h-12 rounded-xl border border-line-strong bg-surface px-3 text-base text-ink" defaultValue="meera">
              <option value="meera">Meera Iyer (+91 98xxxx4410)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-ink-soft">Console key</span>
            <input type="password" defaultValue="sample" className="rounded-lg border border-line-strong bg-canvas px-3 py-2" />
          </label>
          <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4">
            <Meter label="Whisper Score" value={0.93} threshold={0.6} />
            <Meter label="Task Match" value={0.41} threshold={0.7} />
            <Meter label="Spoof Score" value={0.91} advisory />
            <Meter label="Reply Latency" value={null} threshold={1} missed="slow" />
          </div>
        </div>
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------------ phone */

function codeMessage(): DeviceMessage {
  const now = Date.now();
  return {
    id: 1,
    call_id: "sample",
    kind: "possession_code",
    body: { code: "482913", request: "add_payee" },
    created_at: new Date(now - 26_000).toISOString().replace("Z", ""),
    expires_at: new Date(now + 64_000).toISOString().replace("Z", ""),
    seconds_left: 64,
  };
}

function Phone() {
  const [alertKey, setAlertKey] = useState(0);
  const [message] = useState(codeMessage);
  return (
    <Section
      id="phone"
      title="Phone frame and Bank App"
      lead="The Registered Device frame stays dark (bezel) in both themes. The Possession Code card names its Request, groups the digits 3 + 3 and carries the anti-relay line; on the projector the digits are masked and never put in the page. The Security Alert drops in and glows twice."
    >
      <div className="grid gap-6 md:grid-cols-3">
        <div className="mx-auto w-full max-w-[19rem]">
          <DeviceFrame name="Meera Iyer" phone="+91 98xxxx4410">
            <PossessionCode message={message} masked={false} name="Meera Iyer" />
          </DeviceFrame>
          <p className="mt-2 text-center text-xs text-ink-soft">On the Registered Device</p>
        </div>
        <div className="mx-auto w-full max-w-[19rem]">
          <DeviceFrame name="Meera Iyer" phone="+91 98xxxx4410">
            <PossessionCode message={message} masked name="Meera Iyer" />
          </DeviceFrame>
          <p className="mt-2 text-center text-xs text-ink-soft">On the projected hub (stage mode)</p>
        </div>
        <div className="mx-auto w-full max-w-[19rem]">
          <DeviceFrame name="Meera Iyer" phone="+91 98xxxx4410">
            <SecurityAlertPreview key={alertKey} request="add a new payee" />
          </DeviceFrame>
          <div className="mt-2 flex justify-center">
            <ReplayButton onClick={() => setAlertKey((k) => k + 1)} label="Security Alert" />
          </div>
        </div>
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------------ Verdict Ribbon */

const SIGNALS: Signals = {
  transcript: "",
  task_match: null,
  whisper_score: null,
  reply_latency_ms: null,
  spoof_score: null,
  spoken_digits: null,
  code_match: null,
};

function sampleCall(over: Partial<CallView>): CallView {
  const stamp = (ms: number) => new Date(Date.now() - ms).toISOString().replace("Z", "");
  return {
    id: "sample",
    customer: { id: "cust-meera", name: "Meera Iyer" },
    room: "sample",
    state: "challenging",
    request: "add_payee",
    agent_review: false,
    review_status: null,
    challenges: [],
    evidence: [],
    scores: [],
    step_ups: 0,
    verdict: null,
    liveness: null,
    reasons: [],
    outcome: null,
    created_at: stamp(42_000),
    updated_at: stamp(0),
    ...over,
  };
}

const PHRASE = { kind: "whisper_phrase" as const, prompt: "", phrase: "कल सात बजे meeting है" };
const CODE = { kind: "possession_code" as const, prompt: "", phrase: "" };
const WHISPER_OK = {
  kind: "whisper_phrase" as const,
  signals: { ...SIGNALS, task_match: 1, whisper_score: 0.97, reply_latency_ms: 820, spoof_score: 0.91 },
};

/** The demo's beats as sequences of Call states, played at the pace the room would see them. Samples. */
const BEATS: Record<string, [number, () => CallView][]> = {
  "Clone: BLOCK": [
    [0, () => sampleCall({ id: "s-block", state: "awaiting_request", request: null })],
    [1200, () => sampleCall({ id: "s-block", challenges: [PHRASE] })],
    [3000, () => sampleCall({ id: "s-block", challenges: [PHRASE, CODE], evidence: [WHISPER_OK] })],
    [
      5000,
      () =>
        sampleCall({
          id: "s-block", state: "closed", challenges: [PHRASE, CODE],
          evidence: [WHISPER_OK, { kind: "possession_code", signals: { ...SIGNALS, reply_latency_ms: 4100, spoken_digits: "", code_match: null } }],
          verdict: "BLOCK", outcome: "blocked", liveness: 0.62,
          reasons: ["Challenge 2 (Possession Code): no code was read out."],
        }),
    ],
  ],
  "Meera: PASS": [
    [0, () => sampleCall({ id: "s-pass", challenges: [PHRASE] })],
    [1500, () => sampleCall({ id: "s-pass", challenges: [PHRASE, CODE], evidence: [WHISPER_OK] })],
    [
      3500,
      () =>
        sampleCall({
          id: "s-pass", state: "closed", challenges: [PHRASE, CODE],
          evidence: [WHISPER_OK, { kind: "possession_code", signals: { ...SIGNALS, reply_latency_ms: 6200, spoken_digits: "482913", code_match: true } }],
          verdict: "PASS", outcome: "passed", liveness: 0.93, reasons: ["Liveness 0.93 is at or above 0.75."],
        }),
    ],
  ],
  "Call-back: Voice Pause": [
    [
      0,
      () =>
        sampleCall({
          id: "s-pause", state: "closed", verdict: "BLOCK", outcome: "blocked",
          reasons: [
            "A call for this Customer was blocked 1 min ago; voice requests are paused for 30 min or until the Customer dismisses the alert on their Registered Device.",
          ],
        }),
    ],
  ],
};

function Ribbon() {
  const [beat, setBeat] = useState("Clone: BLOCK");
  const [stage, setStage] = useState(false);
  const [run, setRun] = useState(0);
  const [call, setCall] = useState<CallView | null>(null);
  const timers = useRef<number[]>([]);
  useEffect(() => {
    timers.current.forEach(clearTimeout);
    setCall(null);
    timers.current = BEATS[beat].map(([at, make]) => window.setTimeout(() => setCall(make()), at + 300));
    return () => timers.current.forEach(clearTimeout);
  }, [beat, run]);
  return (
    <Section
      id="ribbon"
      title="Verdict Ribbon"
      lead="The projector's one large thing. Neutral while the Call is live; Signal ticks land in order (at least 450 ms apart on stage); then the fill sweeps in and the Verdict word rises. The same layout for PASS and BLOCK. Sample Calls, not live data."
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {Object.keys(BEATS).map((b) => (
          <button
            key={b}
            onClick={() => {
              setBeat(b);
              setRun((r) => r + 1);
            }}
            className={`press rounded-full px-3 py-1.5 text-sm font-medium ${beat === b ? "bg-accent text-on-accent" : "bg-sunken text-ink-soft hover:text-ink"}`}
          >
            {b}
          </button>
        ))}
        <ReplayButton onClick={() => setRun((r) => r + 1)} label="Ribbon" />
        <label className="ml-auto inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={stage} onChange={(e) => setStage(e.target.checked)} className="size-4 accent-accent" />
          Stage size and dwell
        </label>
      </div>
      <div style={stage ? ({ fontSize: "125%" } as CSSProperties) : undefined}>
        <VerdictRibbon key={`${beat}-${run}`} call={call} name="Meera Iyer" stage={stage} />
      </div>
      <p className="mt-3 text-xs text-ink-soft">
        On the projector the whole page is at 125% (every rem), so the word reaches clamp(6rem, 8vw, 9rem). The dwell between
        ticks is skipped under reduced motion.
      </p>
    </Section>
  );
}

/* ------------------------------------------------------------------ motion */

interface MotionSpec {
  name: string;
  timing: string;
  purpose: string;
  demo: (run: number) => ReactNode;
}

const box = "grid h-20 place-items-center rounded-xl border border-line bg-surface text-sm font-medium";

const MOTIONS: MotionSpec[] = [
  {
    name: "enter",
    timing: "280 ms · ease-arrive",
    purpose: "Something arrived: a list item, a panel, a Transcript line.",
    demo: (r) => <div key={r} className={`motion-enter ${box}`}>New Call</div>,
  },
  {
    name: "pop",
    timing: "280 ms · ease-arrive",
    purpose: "A badge appears: the Verdict badge on the Console.",
    demo: (r) => (
      <div className={box}>
        <span key={r} className="motion-pop">
          <VerdictBadge verdict="BLOCK" large />
        </span>
      </div>
    ),
  },
  {
    name: "grow",
    timing: "600 ms · ease-arrive",
    purpose: "A Signal was measured: its meter fills (scaleX).",
    demo: (r) => (
      <div className={`${box} px-4`}>
        <div className="h-2 w-full overflow-hidden rounded-full bg-sunken">
          <div key={r} className="motion-grow h-full origin-left bg-advisory" style={{ transform: "scaleX(0.8)" }} />
        </div>
      </div>
    ),
  },
  {
    name: "ribbon sweep, BLOCK",
    timing: "280 ms laptop, 400 ms stage · ease-firm",
    purpose: "The Verdict lands: the fill sweeps in from the left and the word rises 8 px. No bounce, no shake.",
    demo: (r) => (
      <div key={r} className="ribbon grid h-20 place-items-center rounded-xl text-on-fill" data-verdict="BLOCK">
        <span className="ribbon-word font-display text-2xl font-bold">BLOCKED</span>
      </div>
    ),
  },
  {
    name: "ribbon sweep, PASS + spring",
    timing: "sweep ease-arrive; icon 400 ms · ease-spring",
    purpose: "The PASS icon scales up from 0.6 with a 5% overshoot. Only scale springs; opacity never overshoots.",
    demo: (r) => (
      <div key={r} className="ribbon grid h-20 place-items-center rounded-xl text-on-fill" data-verdict="PASS">
        <span className="ribbon-word inline-flex items-center gap-2 font-display text-2xl font-bold">
          <ShieldCheck weight="fill" size={28} className="ribbon-icon-spring" /> PASS
        </span>
      </div>
    ),
  },
  {
    name: "tick",
    timing: "150 ms · ease-std; mark 200 ms after 150 ms",
    purpose: "A Signal landed on the Ribbon: it fades up 4 px, then its check mark pops.",
    demo: (r) => (
      <div className={box}>
        <span key={r} className="tick inline-flex items-center gap-1.5 rounded-full bg-pass/12 px-3 py-1 text-pass">
          <span className="tick-mark inline-flex">
            <Check size={15} weight="bold" />
          </span>
          Whisper Score 0.97
        </span>
      </div>
    ),
  },
  {
    name: "ring-once",
    timing: "600 ms · ease-arrive, once",
    purpose: "The active Customer's tile: one ring, then stillness.",
    demo: (r) => (
      <div className={`${box} relative text-block`}>
        <span key={r} className="ring-once" />
        <span className="text-ink">Meera</span>
      </div>
    ),
  },
  {
    name: "alert-in + glow",
    timing: "400 ms · ease-arrive; glow 700 ms × 2",
    purpose: "The Security Alert drops in from the top, then glows twice (a pseudo-element's opacity).",
    demo: (r) => (
      <div className="h-20 overflow-hidden rounded-xl border border-line bg-surface p-3">
        <div key={r} className="alert-in rounded-lg border-2 border-block bg-surface px-3 py-2 text-sm font-bold text-block">
          Blocked call attempt
        </div>
      </div>
    ),
  },
  {
    name: "pause scrim + shackle",
    timing: "scrim 700 ms; shackle 150 ms · ease-std",
    purpose: "Voice Pause turns on: the row's tint fades in and the lock's shackle drops 3 px.",
    demo: (r) => (
      <div key={r} className="pause-scrim flex h-20 items-center gap-3 rounded-xl px-4 ring-1 ring-block/45">
        <LockSimple size={24} weight="fill" className="shackle text-block" />
        <span className="text-sm font-semibold text-block">Voice Pause on</span>
      </div>
    ),
  },
  {
    name: "word",
    timing: "200 ms each, 50 ms stagger · ease-arrive",
    purpose: "The Whisper Phrase appears word by word, under 800 ms in all.",
    demo: (r) => (
      <div key={r} className={`${box} font-display text-lg`}>
        <p>
          {"turn left at the blue gate".split(" ").map((w, i) => (
            <span key={i}>
              <span className="word" style={{ "--i": i } as CSSProperties}>{w}</span>{" "}
            </span>
          ))}
        </p>
      </div>
    ),
  },
  {
    name: "motion-fade",
    timing: "150 ms · ease-std",
    purpose: "A live number changed: the value crossfades. Digits never roll.",
    demo: (r) => (
      <div className={`${box} font-mono text-2xl`}>
        <span key={r} className="motion-fade">{(0.5 + ((r * 37) % 50) / 100).toFixed(2)}</span>
      </div>
    ),
  },
  {
    name: "tile dim",
    timing: "400 ms · ease-std (transition)",
    purpose: "On stage, the Customers not on the latest Call step back to 55%. Replay toggles it.",
    demo: (r) => (
      <div className={box}>
        <span className={`tile rounded-lg bg-sunken px-3 py-2 ${r % 2 ? "is-dim" : ""}`}>Rahul's tile</span>
      </div>
    ),
  },
  {
    name: "voice + breathe, loop",
    timing: "900 ms alternate · ease-loop",
    purpose: "Someone is speaking right now. Static bars under reduced motion.",
    demo: () => (
      <div className={`${box} text-turn-bank`}>
        <span className="voice-bars is-active">
          <span />
          <span />
          <span />
          <span />
          <span />
        </span>
      </div>
    ),
  },
  {
    name: "live, loop",
    timing: "2 s · ease-arrive",
    purpose: "A live connection, or a Call in progress.",
    demo: () => (
      <div className={`${box} text-accent`}>
        <span className="inline-flex items-center gap-2">
          <span className="live-dot" /> Live
        </span>
      </div>
    ),
  },
  {
    name: "spin, loop",
    timing: "900 ms per turn · linear",
    purpose: "Checking: the Verifier is scoring a Response.",
    demo: () => (
      <div className={`${box} text-turn-wait`}>
        <CircleNotch size={32} weight="bold" className="spinner" />
      </div>
    ),
  },
  {
    name: "typing, loop",
    timing: "1.2 s · ease-loop",
    purpose: "The Voice Agent is about to speak (Console Transcript).",
    demo: () => (
      <div className={`${box} text-accent`}>
        <span className="typing inline-flex gap-1">
          <span />
          <span />
          <span />
        </span>
      </div>
    ),
  },
  {
    name: "shimmer, loop",
    timing: "1.4 s · ease-loop",
    purpose: "Loading: a skeleton in the shape of what is coming.",
    demo: () => (
      <div className="flex h-20 flex-col justify-center gap-2 rounded-xl border border-line bg-surface p-4">
        <div className="skeleton h-3 w-3/4" />
        <div className="skeleton h-3 w-1/2" />
      </div>
    ),
  },
  {
    name: "press",
    timing: "100 ms · ease-std (transition)",
    purpose: "Tactile feedback: scale 0.98 while pressed.",
    demo: () => (
      <div className={box}>
        <button className="press rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent">Press me</button>
      </div>
    ),
  },
];

function MotionCatalogue() {
  const [runs, setRuns] = useState<number[]>(() => MOTIONS.map(() => 0));
  const reduced = prefersReducedMotion();
  return (
    <Section
      id="motion"
      title="Motion"
      lead="Every animation in the app, by name. Only transform and opacity move. Expressive motion is kept for the Verdict and the Security Alert; everything else is productive. Loops run only for real live states. Under reduced motion every animation completes in 1 ms and loops stop; the Ribbon and the Security Alert keep a 150 ms crossfade."
    >
      {reduced && <p className="mb-4 rounded-lg bg-sunken px-3 py-2 text-sm">Reduced motion is on: replays finish at once.</p>}
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {MOTIONS.map((m, i) => (
          <li key={m.name} className="flex flex-col gap-3 rounded-xl border border-line bg-canvas p-3">
            {m.demo(runs[i])}
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-mono text-sm font-semibold">{m.name}</p>
                <p className="font-mono text-xs text-ink-soft">{m.timing}</p>
                <p className="mt-1 text-sm leading-snug text-ink-soft">{m.purpose}</p>
              </div>
              <ReplayButton onClick={() => setRuns((r) => r.map((v, k) => (k === i ? v + 1 : v)))} label={m.name} compact />
            </div>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ReplayButton({ onClick, label, compact = false }: { onClick: () => void; label: string; compact?: boolean }) {
  return (
    <button
      onClick={onClick}
      aria-label={`Replay ${label}`}
      className={`press inline-flex shrink-0 items-center gap-1.5 rounded-lg text-sm font-medium text-ink-soft ring-1 ring-line hover:text-ink ${
        compact ? "size-9 justify-center" : "px-3 py-1.5"
      }`}
    >
      {compact ? (
        <ArrowCounterClockwise size={16} />
      ) : (
        <>
          <Play size={15} weight="fill" /> Replay
        </>
      )}
    </button>
  );
}
