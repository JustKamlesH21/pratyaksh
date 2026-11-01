import { useEffect, useRef, useState } from "react";
import { Microphone, ShieldWarning, Stop, Waveform } from "@phosphor-icons/react";
import { api } from "../api";
import { ErrorNote } from "../components";
import type { MyVoice as Mine, VoiceConsent } from "../types";
import { type Recording, startRecording } from "../wavRecorder";

const MAX_RECORDING_S = 30;

export function timeLeft(seconds: number): string {
  if (seconds >= 3600) return `${Math.ceil(seconds / 3600)} h`;
  if (seconds >= 60) return `${Math.ceil(seconds / 60)} min`;
  return `${seconds} s`;
}

/** The Bank App's My voice section: requests to use the Customer's voice, what is in force, and what was refused.
 *  Consent is given only here, on the Registered Device, by reading the statement aloud. */
export function MyVoice({ customer, device }: { customer: string; device: string }) {
  const [mine, setMine] = useState<Mine | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => api.myVoice(customer, device).then(setMine, (e) => setError(String(e)));
  useEffect(() => {
    let alive = true;
    const tick = () => api.myVoice(customer, device).then((m) => alive && setMine(m), () => {});
    tick();
    const id = setInterval(tick, 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [customer, device]);

  async function once(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const pending = mine?.consents.filter((c) => c.status === "pending").slice(0, 1) ?? []; // newest first: one at a time
  const active = mine?.consents.filter((c) => c.status === "active" || c.status === "used_up") ?? [];
  const refused = mine?.refused.slice(0, 3) ?? [];
  return (
    <section aria-label="My voice" className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2 font-semibold"><Waveform size={19} className="text-accent" aria-hidden /> My voice</h2>
      <ErrorNote error={error} />
      {pending.map((c) => (
        <Request key={c.id} consent={c} customer={customer} device={device} onDone={refresh} onError={setError} />
      ))}
      {active.map((c) => (
        <div key={c.id} className="rounded-2xl border border-line bg-surface p-4">
          <p className="text-sm font-semibold">{c.requester}</p>
          <p className="text-sm text-ink-soft">for {c.purpose_label}</p>
          <p className="mt-1 text-xs text-ink-soft">
            {c.uses} of {c.max_uses} uses, {timeLeft(c.seconds_left)} left
          </p>
          <button className="btn btn-danger mt-3 w-full text-ink" disabled={busy}
            onClick={() => once(() => api.revokeConsent(c.id, customer, device))}>
            Revoke now
          </button>
        </div>
      ))}
      {mine && pending.length === 0 && active.length === 0 && (
        <p className="text-sm text-ink-soft">Nobody has your permission to use your voice.</p>
      )}
      {refused.map((e) => (
        <div key={e.seq} className="flex gap-2 rounded-xl bg-block/10 px-3.5 py-2.5 text-sm">
          <ShieldWarning size={18} className="mt-0.5 shrink-0 text-block" aria-hidden />
          <p className="text-ink">
            <b>{e.requester}</b> was stopped from using your voice: {e.reason}.
          </p>
        </div>
      ))}
    </section>
  );
}

function Request({ consent: c, customer, device, onDone, onError }: {
  consent: VoiceConsent;
  customer: string;
  device: string;
  onDone: () => unknown;
  onError: (e: string | null) => void;
}) {
  const [phase, setPhase] = useState<"idle" | "recording" | "checking">("idle");
  const [seconds, setSeconds] = useState(0);
  const [retry, setRetry] = useState<string | null>(null);
  const recording = useRef<Recording | null>(null);

  useEffect(() => () => recording.current?.cancel(), []);

  useEffect(() => {
    if (phase !== "recording") return;
    setSeconds(0);
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [phase]);

  useEffect(() => {
    if (phase === "recording" && seconds >= MAX_RECORDING_S) void finish();
  }, [seconds, phase]);

  async function begin() {
    onError(null);
    setRetry(null);
    try {
      recording.current = await startRecording();
      setPhase("recording");
    } catch (e) {
      onError(`The microphone could not start: ${e}`);
    }
  }

  async function finish() {
    const r = recording.current;
    if (!r) return;
    recording.current = null;
    setPhase("checking");
    try {
      const result = await api.giveConsent(c.id, customer, device, await r.stop());
      if (!result.granted) setRetry(result.reason ?? "Please read it again.");
      await onDone();
    } catch (e) {
      onError(String(e));
    } finally {
      setPhase("idle");
    }
  }

  const [sentence, number] = c.statement.split(" Number ");
  return (
    <div className="motion-enter rounded-2xl border-2 border-accent bg-surface p-4">
      <p className="font-bold">{c.requester} wants to use your voice</p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
        <dt className="text-ink-soft">For</dt><dd className="min-w-0 font-medium">{c.purpose_label}</dd>
        <dt className="text-ink-soft">Lasts</dt><dd className="font-medium">{timeLeft(c.minutes * 60)}</dd>
        <dt className="text-ink-soft">Up to</dt><dd className="font-medium">{c.max_uses} uses</dd>
      </dl>
      <p className="mt-3 text-xs font-medium text-ink-soft">To agree, read this aloud, slowly:</p>
      <div className="mt-1 rounded-xl bg-sunken p-3 font-medium leading-snug">
        <p>{sentence}</p>
        <p className="mt-2 text-xl font-bold">Number {number}</p>
      </div>
      {retry && <p className="mt-2 text-sm font-medium text-block">{retry}</p>}
      <p className="mt-2 text-xs text-ink-soft">Expires in {c.seconds_left}s</p>
      {/* Stacked, not side by side: two large pills do not fit the embedded phone's width. */}
      <div className="mt-3 flex flex-col gap-2">
        {phase === "recording" ? (
          <button className="btn btn-primary btn-lg w-full px-3" onClick={finish}>
            <Stop size={18} weight="fill" aria-hidden /> Finished · {seconds}s
          </button>
        ) : (
          <>
            <button className="btn btn-primary btn-lg w-full px-3" disabled={phase === "checking"} onClick={begin}>
              <Microphone size={18} aria-hidden /> {phase === "checking" ? "Checking" : "Read aloud"}
            </button>
            <button className="btn btn-danger w-full px-3 text-ink" disabled={phase === "checking"}
              onClick={() => api.declineConsent(c.id, customer, device).then(onDone, (e) => onError(String(e)))}>
              Decline
            </button>
          </>
        )}
      </div>
    </div>
  );
}
