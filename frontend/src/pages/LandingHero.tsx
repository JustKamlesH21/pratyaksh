/* The landing hero's moving picture: a replay of a blocked Clone Call, as the product shows it. A cloned
   voice asks for a new payee, passes the Task Match and the whispered phrase, cannot read the Possession
   Code that sits only on Rahul's real phone, and is BLOCKed; the phone then shows the Security Alert.
   It is labelled a replay (scripted from our own test Calls, no numbers it did not measure), loops while
   on screen, pauses off screen, and under reduced motion shows its last frame and stays there. */
import { type CSSProperties, useEffect, useRef, useState } from "react";
import { Check, DeviceMobile, Play, ShieldCheck, X } from "@phosphor-icons/react";
import { Logo, VerdictBadge, prefersReducedMotion, scriptLang } from "../components";
import { DeviceFrame, PossessionCodePreview, SecurityAlertPreview } from "./LandingParts";

type Voice = "ring" | "caller" | "agent" | "whisper" | "quiet";
interface Beat {
  ms: number;
  voice: Voice;
  who?: string;
  text?: string;
  ticks: number; // how many Signals have landed
  code: boolean; // Possession Code sent to the real phone
  verdict: boolean;
}

const BEATS: Beat[] = [
  { ms: 1300, voice: "ring", ticks: 0, code: false, verdict: false },
  { ms: 2700, voice: "caller", who: "Caller (cloned voice)", text: "नमस्ते, मुझे नया payee add करना है", ticks: 0, code: false, verdict: false },
  { ms: 3100, voice: "agent", who: "Voice Agent", text: "Two quick checks first. Please whisper these words: कल सात बजे meeting है", ticks: 1, code: false, verdict: false },
  { ms: 2400, voice: "whisper", who: "Caller (cloned voice)", text: "कल सात बजे meeting है", ticks: 1, code: false, verdict: false },
  { ms: 2900, voice: "agent", who: "Voice Agent", text: "Thank you. Now read the code shown in your bank app.", ticks: 2, code: true, verdict: false },
  { ms: 2500, voice: "caller", who: "Caller (cloned voice)", text: "मुझे कोड नहीं मिला", ticks: 2, code: true, verdict: false },
  { ms: 6200, voice: "quiet", ticks: 3, code: true, verdict: true },
];
const LAST = BEATS.length - 1;

const SIGNALS: [string, string, boolean][] = [
  ["Task Match", "meets", true],
  ["Whisper Score", "meets", true],
  ["Possession Code", "not read", false],
];

// Bar heights for the waveform: a fixed, speech-like envelope (no randomness, so every replay matches).
const BARS = Array.from({ length: 44 }, (_, i) => {
  const env = Math.sin((Math.PI * (i + 0.5)) / 44) ** 0.6;
  const wobble = 0.55 + 0.45 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * 0.6));
  return Math.max(0.12, env * wobble);
});

/** True while the element is at least partly on screen (unlike useInView, it turns false again). */
function useOnScreen<T extends Element>() {
  const ref = useRef<T>(null);
  const [on, setOn] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => setOn(e.isIntersecting));
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return [ref, on] as const;
}

export function HeroReel() {
  const reduced = prefersReducedMotion();
  const [beat, setBeat] = useState(reduced ? LAST : 0);
  const [round, setRound] = useState(0); // remounts the captions on each replay
  const [ref, onScreen] = useOnScreen<HTMLElement>();

  useEffect(() => {
    if (reduced || !onScreen) return;
    const id = setTimeout(() => {
      if (beat === LAST) {
        setBeat(0);
        setRound((r) => r + 1);
      } else setBeat(beat + 1);
    }, BEATS[beat].ms);
    return () => clearTimeout(id);
  }, [beat, onScreen, reduced]);

  const b = BEATS[beat];
  const at = BEATS.slice(0, beat).reduce((s, x) => s + x.ms, 0) / 1000;
  const live = !b.verdict;

  return (
    <figure
      ref={ref}
      className="mx-auto flex w-full max-w-xl flex-col items-center gap-5 xl:max-w-none xl:flex-row xl:items-end"
      aria-label="Replay: a cloned voice calls as Rahul Verma and is blocked"
    >
      <div
        data-verdict={b.verdict ? "BLOCK" : undefined}
        className="hero-card elev-2 relative w-full min-w-0 flex-1 overflow-hidden rounded-[1.75rem] border border-line bg-surface"
      >
        {/* header: what this is, honestly */}
        <div className="flex items-center gap-3 border-b border-line px-5 py-3.5">
          <Logo size={28} />
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-sm font-semibold">Add payee · as Rahul Verma</p>
            <p className="flex items-center gap-1.5 text-xs text-ink-soft">
              <Play size={11} weight="fill" aria-hidden /> Replay of a blocked Clone Call
            </p>
          </div>
          <span className="font-mono text-sm text-ink-soft" aria-hidden>
            0:{String(Math.floor(at)).padStart(2, "0")}
          </span>
        </div>

        {/* the voice on the line */}
        <div className="px-5 pt-6">
          <div
            className={`hero-wave is-${b.voice} ${b.voice === "agent" ? "text-accent" : b.voice === "ring" || b.voice === "quiet" ? "text-line-strong" : "text-ink"}`}
            aria-hidden
          >
            {BARS.map((a, i) => (
              <span key={i} style={{ "--a": a, "--i": i, "--d": `${620 + ((i * 97) % 380)}ms` } as CSSProperties} />
            ))}
          </div>
          <p className="mt-2 flex h-5 items-center gap-2 text-xs font-medium text-ink-soft">
            {b.voice === "ring" && <><span className="live-dot text-accent" aria-hidden /> Incoming call to the bank</>}
            {b.voice === "whisper" && "Whispering"}
            {(b.voice === "caller" || b.voice === "agent") && b.who}
            {b.voice === "whisper" && <span className="text-ink-soft">· {b.who}</span>}
            {b.voice === "quiet" && "Call ended by the Policy"}
          </p>
        </div>

        {/* what was said, word by word */}
        <div className="min-h-[5.5rem] px-5 pt-3" aria-live="polite">
          {b.text && (
            <p key={`${round}-${beat}`} className="font-display text-[1.4rem] font-medium leading-snug tracking-[-0.01em]" lang={scriptLang(b.text)}>
              {b.text.split(" ").map((w, i, all) => (
                <span key={i}>
                  <span className="caption-word" style={{ "--i": i, "--step": "70ms" } as CSSProperties}>{w}</span>
                  {i < all.length - 1 ? " " : ""}
                </span>
              ))}
            </p>
          )}
          {b.verdict && (
            <div key={`v-${round}`} className="flex items-center gap-3">
              <VerdictBadge verdict="BLOCK" large />
              <p className="motion-enter text-sm leading-snug text-ink-soft">
                Same voice. No code. <span className="text-ink">Nothing was changed.</span>
              </p>
            </div>
          )}
        </div>

        {/* Signals land one by one */}
        <ul className="grid grid-cols-3 gap-2 px-5 pb-5 pt-4" aria-label="Signals">
          {SIGNALS.map(([name, value, ok], k) => {
            const landed = k < b.ticks;
            return (
              <li
                key={name}
                className={`rounded-xl px-3 py-2.5 ${landed ? (ok ? "bg-sunken" : "bg-block/12 ring-1 ring-block/40") : "bg-sunken/60"}`}
              >
                <p className="truncate text-[0.7rem] font-medium text-ink-soft">{name}</p>
                <p className={`mt-0.5 flex h-5 items-center gap-1 font-mono text-xs font-semibold ${landed ? (ok ? "text-ink" : "text-block") : "text-ink-soft"}`}>
                  {landed ? (
                    <span key={`${round}-${k}`} className="tick inline-flex items-center gap-1">
                      {ok ? <Check size={13} weight="bold" className="tick-mark" aria-hidden /> : <X size={13} weight="bold" className="tick-mark" aria-hidden />}
                      {value}
                    </span>
                  ) : (
                    "waiting"
                  )}
                </p>
              </li>
            );
          })}
        </ul>

        {live && b.code && (
          <p className="motion-enter flex items-center gap-2 border-t border-line px-5 py-3 text-xs text-ink-soft">
            <DeviceMobile size={15} className="text-accent" aria-hidden /> Possession Code sent to Rahul's real phone. The Clone never sees it.
          </p>
        )}
      </div>

      {/* Rahul's real phone, in his pocket the whole time: idle, then the code, then the Security Alert */}
      <div className="hero-phone is-in w-[15rem] shrink-0 xl:-mb-10">
        <DeviceFrame name="Rahul Verma" phone="+91 99xxxx2087">
          {b.verdict ? (
            <SecurityAlertPreview key={`a-${round}`} request="add a new payee" className="text-sm" />
          ) : b.code ? (
            <div key={`c-${round}`} className="motion-enter">
              <PossessionCodePreview code="481927" request="Add payee" compact />
            </div>
          ) : (
            <div className="flex min-h-[13.5rem] flex-col items-center justify-center gap-3 text-center">
              <ShieldCheck size={30} className="text-accent" aria-hidden />
              <p className="text-sm text-ink-soft">No requests right now.</p>
            </div>
          )}
        </DeviceFrame>
      </div>
    </figure>
  );
}
