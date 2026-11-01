import { useEffect, useRef, useState } from "react";
import { CheckCircle, Copy, DeviceMobile, Play, Prohibit, SealCheck, ShieldCheck, Waveform } from "@phosphor-icons/react";
import { HttpError, api, setConsoleKey } from "../api";
import { Card, ErrorNote, KeyGate, PageHeader, scriptLang } from "../components";
import type { ConsentOverview, DemoCustomer, LedgerEvent, VoiceConsent } from "../types";
import { BankApp } from "./BankAppPage";
import { timeLeft } from "./MyVoice";

// The requester's side of Voice Consent: ask for a person's voice, then try to use it. Consent itself is given on
// the owner's phone, on the right. A person presses play every time; this page only releases consented recordings
// and nothing here synthesises speech.

const LABEL: Record<LedgerEvent["kind"], string> = {
  consent_requested: "Consent requested",
  consent_statement_failed: "Statement not clearly heard",
  consent_granted: "Consent given by voice",
  consent_declined: "Consent declined",
  consent_revoked: "Consent revoked by the owner",
  voice_use_allowed: "Voice used",
  voice_use_refused: "Use refused",
};
const DURATIONS = [[15, "15 minutes"], [60, "1 hour"], [1440, "1 day"]] as const;
const USES = [5, 20, 50];
const STRANGER = "Shady Ads Ltd";

type Attempt = "agreed" | "purpose" | "company" | "none";
type Result = { allowed: boolean; title: string; detail: string };
type Held = { pass: string; requester: string; purpose: string };

export default function ConsentPage() {
  const [keyVersion, setKeyVersion] = useState(0);
  const [locked, setLocked] = useState(false);
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  const [ownerId, setOwnerId] = useState("cust-rahul");
  const [seen, setSeen] = useState<ConsentOverview | null>(null);
  const [requester, setRequester] = useState("Omnitrons Lab");
  const [purpose, setPurpose] = useState("security_test");
  const [minutes, setMinutes] = useState(60);
  const [maxUses, setMaxUses] = useState(20);
  const [clip, setClip] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const player = useRef<HTMLAudioElement | null>(null);
  // The pass the requester holds. It stays here after a revoke, which is the point: it still looks valid, and is refused.
  const held = useRef<Record<string, Held>>({});

  useEffect(() => {
    api.demoCustomers().then(setCustomers, () => setLocked(true));
  }, [keyVersion]);

  useEffect(() => {
    let alive = true;
    const tick = () =>
      api.consentOverview().then(
        (o) => {
          if (!alive) return;
          setSeen(o);
          for (const c of [...o.consents].reverse()) {
            if (c.consent_pass) held.current[c.customer_id] = { pass: c.consent_pass, requester: c.requester, purpose: c.purpose };
          }
        },
        (e) => alive && e instanceof HttpError && e.status === 403 && setLocked(true),
      );
    tick();
    const id = setInterval(tick, 1500);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [keyVersion]);

  useEffect(() => {
    if (!clip && seen?.clips.length) setClip(seen.clips.find((c) => c.kind === "clone")?.id ?? seen.clips[0].id);
  }, [seen, clip]);

  if (locked)
    return (
      <KeyGate
        why="This page releases recordings of a person's voice, so it is for staff."
        onKey={(key) => {
          setConsoleKey(key);
          setLocked(false);
          setKeyVersion((v) => v + 1);
        }}
      />
    );

  const owner = customers.find((c) => c.id === ownerId);
  const first = owner?.name.split(" ")[0] ?? "the owner";
  const mine = seen?.consents.filter((c) => c.customer_id === ownerId) ?? [];
  const latest = mine[0] ?? null;
  const pass = latest?.consent_pass ?? null;

  async function ask() {
    setError(null);
    setResult(null);
    try {
      await api.askConsent({ customer_id: ownerId, requester, purpose, minutes, max_uses: maxUses });
      setSeen(await api.consentOverview());
    } catch (e) {
      setError(String(e));
    }
  }

  async function attempt(kind: Attempt) {
    if (busy || !clip) return;
    setBusy(true);
    setError(null);
    player.current?.pause();
    const got = held.current[ownerId];
    const asked = {
      customer_id: ownerId,
      clip,
      requester: kind === "company" ? STRANGER : (got?.requester ?? requester),
      purpose: kind === "purpose" ? (got?.purpose === "advertising" ? "security_test" : "advertising") : (got?.purpose ?? purpose),
      consent_pass: kind === "none" ? null : (got?.pass ?? null),
    };
    const wanted = seen?.purposes.find((p) => p.id === asked.purpose)?.label ?? asked.purpose;
    const who = `${asked.requester}, for ${wanted}`;
    try {
      const audio = new Audio(URL.createObjectURL(await api.useVoice(asked)));
      player.current = audio;
      setResult({ allowed: true, title: "Allowed: playing", detail: who });
      await audio.play();
    } catch (e) {
      if (e instanceof HttpError && e.status === 403) setResult({ allowed: false, title: "Refused", detail: `${who}: ${e.detail}` });
      else setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function copyPass() {
    if (!pass) return;
    await navigator.clipboard.writeText(pass);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Your voice, your permission"
        actions={
          <>
            <label className="text-xs text-ink-soft" htmlFor="owner">Voice owner</label>
            <select id="owner" value={ownerId} onChange={(e) => { setOwnerId(e.target.value); setResult(null); }}
              className="field min-h-10 rounded-full text-sm">
              {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </>
        }
      >
        The owner decides who may use their voice, for what, for how long and how many times. They agree on their own
        phone by reading a statement with a fresh number. Every use is checked, logged and can be stopped at once.
      </PageHeader>

      <ErrorNote error={error} />

      {/* The tall phone spans both rows; the Voice Ledger, the proof, sits under the two steps beside it. */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_22rem] lg:grid-rows-[auto_minmax(0,1fr)]">
        <Card title={<span className="flex items-center gap-2"><SealCheck size={18} aria-hidden /> 1. Ask for consent</span>}>
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-ink-soft">Who is asking</span>
              <input className="field" value={requester} maxLength={60} onChange={(e) => setRequester(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-ink-soft">For what</span>
              <select className="field" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                {seen?.purposes.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-ink-soft">For how long</span>
                <select className="field" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
                  {DURATIONS.map(([m, text]) => <option key={m} value={m}>{text}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-ink-soft">How many uses</span>
                <select className="field" value={maxUses} onChange={(e) => setMaxUses(Number(e.target.value))}>
                  {USES.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
            </div>
            <button className="btn btn-primary btn-lg" disabled={!owner} onClick={ask}>Send to {first}'s phone</button>
            {latest && <Consent consent={latest} />}
            {pass && (
              <button className="btn btn-quiet btn-sm self-start" onClick={copyPass}>
                <Copy size={15} aria-hidden /> {copied ? "Copied" : "Copy Consent Pass"}
              </button>
            )}
          </div>
        </Card>

        <Card title={<span className="flex items-center gap-2"><Waveform size={18} aria-hidden /> 2. Try to use the voice</span>}>
          <div className="flex flex-col gap-3">
            {seen && seen.clips.length === 0 && <p className="text-sm text-ink-soft">No recordings set: fill in CLONE_MANIFEST in .env.</p>}
            <fieldset className="flex flex-col gap-1.5" aria-label="Recording">
              {seen?.clips.map((c) => (
                <label key={c.id}
                  className={`flex cursor-pointer gap-2.5 rounded-xl border p-2.5 text-sm ${clip === c.id ? "border-accent bg-accent/10" : "border-line"}`}>
                  <input type="radio" name="clip" checked={clip === c.id} onChange={() => setClip(c.id)} className="mt-1 accent-[var(--color-accent)]" />
                  <span className="min-w-0">
                    <span className="block text-xs font-semibold text-ink-soft">{c.kind === "real" ? "Real voice" : "AI clone (synthetic)"}</span>
                    <span lang={scriptLang(c.label)}>{c.kind === "real" ? "The consented recording" : c.label}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            <div className="grid grid-cols-2 gap-2">
              <button className="btn btn-primary col-span-2" disabled={busy || !clip} onClick={() => attempt("agreed")}>
                <Play size={16} weight="fill" aria-hidden /> Use it as agreed
              </button>
              <button className="btn btn-quiet" disabled={busy || !clip} onClick={() => attempt("purpose")}>Another purpose</button>
              <button className="btn btn-quiet" disabled={busy || !clip} onClick={() => attempt("company")}>Another company</button>
              <button className="btn btn-quiet col-span-2" disabled={busy || !clip} onClick={() => attempt("none")}>No Consent Pass at all</button>
            </div>
            {result && (
              <div key={`${result.title}${result.detail}`} aria-live="polite"
                className={`motion-pop flex gap-2.5 rounded-xl p-3.5 ${result.allowed ? "bg-pass/10" : "bg-block/10"}`}>
                {result.allowed
                  ? <CheckCircle size={22} weight="fill" className="shrink-0 text-pass" aria-hidden />
                  : <Prohibit size={22} weight="bold" className="shrink-0 text-block" aria-hidden />}
                <div className="min-w-0">
                  <p className={`font-bold ${result.allowed ? "text-pass" : "text-block"}`}>{result.title}</p>
                  <p className="text-sm text-ink">{result.detail}</p>
                </div>
              </div>
            )}
          </div>
        </Card>

        <section aria-label={`${first}'s phone`} className="elev-1 flex flex-col gap-3 rounded-2xl border border-line bg-surface p-5 lg:row-span-2">
          <h2 className="flex items-center gap-2 font-semibold"><DeviceMobile size={18} aria-hidden /> {first}'s phone</h2>
          <p className="-mt-2 text-sm text-ink-soft">Consent is given here, by reading aloud.</p>
          {owner ? <BankApp customer={owner.id} device={owner.device_token} embedded tall maskCodes /> : <p className="text-sm text-ink-soft">Loading…</p>}
        </section>

        <Card
          className="min-w-0 lg:col-span-2"
          title={
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              Voice Ledger
              {seen && (
                <span className={`inline-flex items-center gap-1 text-xs font-semibold ${seen.ledger_intact ? "text-pass" : "text-block"}`}>
                  <ShieldCheck size={15} aria-hidden /> {seen.ledger_intact ? "Hash chain intact" : "Hash chain broken"}
                </span>
              )}
            </span>
          }
        >
          {!seen?.ledger.length && <p className="text-sm text-ink-soft">Nothing yet. Every request and every use appears here.</p>}
          <ol className="flex max-h-80 flex-col divide-y divide-line overflow-y-auto">
            {seen?.ledger.map((e) => (
              <li key={`${e.customer_name}${e.seq}`} className="grid gap-x-4 py-2 text-sm sm:grid-cols-[6rem_1fr_auto]">
                <span className="font-mono text-xs text-ink-soft">{new Date(e.at + "Z").toLocaleTimeString()}</span>
                <span className="min-w-0">
                  <b className={e.kind === "voice_use_refused" ? "text-block" : ""}>{LABEL[e.kind]}</b>
                  <span className="text-ink-soft">: {e.customer_name}{e.requester ? `, ${e.requester}` : ""}{e.reason ? `, ${e.reason}` : ""}</span>
                </span>
                <span className="font-mono text-xs text-ink-soft">{e.hash}</span>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}

const STATUS: Record<VoiceConsent["status"], string> = {
  pending: "Waiting for the owner",
  active: "Consent Pass issued",
  used_up: "All uses spent",
  declined: "Declined by the owner",
  revoked: "Revoked by the owner",
  lapsed: "Not answered in time",
  expired: "Expired",
};

function Consent({ consent: c }: { consent: VoiceConsent }) {
  const live = c.status === "active";
  return (
    <div className="rounded-xl bg-sunken p-3.5 text-sm">
      <p className={`font-bold ${live ? "text-pass" : c.status === "pending" ? "text-accent" : "text-ink"}`}>{STATUS[c.status]}</p>
      <p className="text-ink-soft">{c.requester}, for {c.purpose_label}</p>
      {live && (
        <p className="mt-1 text-xs text-ink-soft">
          {c.uses} of {c.max_uses} uses, {timeLeft(c.seconds_left)} left
          {c.statement_match != null && `, statement match ${c.statement_match.toFixed(2)}`}
        </p>
      )}
    </div>
  );
}
