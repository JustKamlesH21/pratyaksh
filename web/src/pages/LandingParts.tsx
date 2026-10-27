/* Landing-only building blocks. The previews below reuse the markup and classes of the real screens
   (Bank App inbox, Console Transcript lines, VerdictBadge, Meter) so the landing page shows the product
   as it looks, not a drawing of it. Numbers shown in them are the ones we measured (docs/BUILD_PROMPT.md,
   docs/BUSINESS.md) or read from policy.yaml. */
import { type CSSProperties, type ReactNode, type RefObject, useEffect, useRef, useState } from "react";
import { Bank, Password, Siren, User, Waveform } from "@phosphor-icons/react";
import { prefersReducedMotion } from "../components";

/** True once the element has scrolled into view (IntersectionObserver, no scroll listener).
 *  Starts true under reduced motion, so nothing waits on scrolling. */
export function useInView<T extends Element>(rootMargin = "0px 0px -15% 0px"): [RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(prefersReducedMotion);
  useEffect(() => {
    if (seen) return;
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
      { rootMargin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [seen, rootMargin]);
  return [ref, seen];
}

/** The Bank App's phone frame and header, as on /bank. */
export function DeviceFrame({ name, phone, children, className = "" }: {
  name: string;
  phone: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`overflow-hidden rounded-[2.2rem] border-[10px] border-zinc-900 bg-surface ring-1 ring-line ${className}`}>
      <div className="bg-accent px-5 pb-5 pt-6 text-on-color">
        <p className="flex items-center gap-1.5 text-xs font-medium opacity-80"><Bank size={15} /> Your bank</p>
        <p className="text-lg font-bold">{name}</p>
        <p className="text-sm opacity-80">{phone}</p>
      </div>
      <div className="flex flex-col gap-4 p-5">{children}</div>
    </div>
  );
}

/** The Security Alert card from the Bank App inbox (the Dismiss button is shown, not wired). */
export function SecurityAlertPreview({ request, className = "" }: { request: string; className?: string }) {
  return (
    <div className={`rounded-xl border-2 border-block bg-block/10 p-4 ${className}`}>
      <p className="flex items-center gap-2 font-bold text-block"><Siren size={20} /> Blocked call attempt</p>
      <p className="mt-1 text-sm text-ink">
        Someone called the bank as you and asked to <b>{request}</b>. We could not verify them, so nothing was changed.
      </p>
      <p className="mt-1 text-xs text-ink-soft">
        Voice requests on your account are paused until you dismiss this. Never share codes with anyone.
      </p>
      <span className="mt-3 block w-full rounded-lg bg-surface py-3 text-center font-bold text-ink ring-1 ring-block/40" aria-hidden>
        Dismiss
      </span>
    </div>
  );
}

/** The Possession Code card from the Bank App inbox. Digits arrive one by one when revealed. */
export function PossessionCodePreview({ code }: { code: string }) {
  return (
    <div className="rounded-xl bg-sunken p-4 text-center">
      <p className="flex items-center justify-center gap-1.5 text-sm text-ink-soft"><Password size={17} /> One-time code for your call with the bank</p>
      <p className="my-2 font-mono text-4xl font-semibold tracking-[0.3em] text-ink" aria-label={code.split("").join(" ")}>
        {code.split("").map((d, i) => (
          <span key={i} className="lp-digit inline-block" style={{ "--i": i } as CSSProperties} aria-hidden>{d}</span>
        ))}
      </p>
      <p className="mt-2 text-xs text-ink-soft">Read it out on the call.</p>
    </div>
  );
}

/** A Voice Agent line, styled as in the Console Transcript. */
export function AgentLine({ children }: { children: ReactNode }) {
  return (
    <div className="flex max-w-[92%] items-start gap-2.5">
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent/12 text-accent" aria-hidden>
        <Waveform size={17} />
      </span>
      <div className="min-w-0">
        <p className="mb-1 text-xs text-ink-soft">Voice Agent</p>
        <p className="rounded-2xl rounded-tl-sm bg-sunken px-3.5 py-2 leading-relaxed">{children}</p>
      </div>
    </div>
  );
}

/** A Caller line with its chips, styled as in the Console Transcript. chips: [text, colour class]. */
export function CallerLine({ who = "Caller", text, chips = [] }: { who?: string; text: ReactNode; chips?: [string, string][] }) {
  return (
    <div className="ml-auto flex max-w-[92%] flex-row-reverse items-start gap-2.5">
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-sunken text-ink-soft" aria-hidden>
        <User size={17} />
      </span>
      <div className="flex min-w-0 flex-col items-end">
        <p className="mb-1 text-xs text-ink-soft">{who}</p>
        <p className="rounded-2xl rounded-tr-sm bg-accent/12 px-3.5 py-2 leading-relaxed ring-1 ring-accent/20">{text}</p>
        {chips.length > 0 && (
          <p className="mt-1.5 flex flex-wrap justify-end gap-1">
            {chips.map(([t, cls]) => (
              <span key={t} className={`rounded-full bg-sunken px-2 py-0.5 font-mono text-[0.68rem] ${cls || "text-ink-soft"}`}>{t}</span>
            ))}
          </p>
        )}
      </div>
    </div>
  );
}

/** A source link under a cited figure. */
export function Source({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-xs text-ink-soft underline decoration-line underline-offset-4 hover:text-ink hover:decoration-accent"
    >
      {children}
    </a>
  );
}
