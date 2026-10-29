import { useEffect, useMemo, useState } from "react";
import { CheckCircle, Circle, DeviceMobile, Robot, XCircle } from "@phosphor-icons/react";
import { api, setConsoleKey } from "../api";
import { KeyGate, useLiveCalls } from "../components";
import type { CallView, DemoCustomer, TranscriptLine } from "../types";
import { T, isVoicePauseRefusal, noLiveMic } from "../verdict";
import { BankApp } from "./BankAppPage";
import { VerdictRibbon } from "./DemoPage";

// The Deepfake tab: a read-only live view of a Clone attack. A person still opens the Caller page as the
// victim (microphone: the virtual cable) and plays each Clone line (attacker/demo_clone.py); this page
// only SHOWS what the Voice Agent and the verifier do with it: both sides of the Call, the Possession Code
// landing on the victim's real phone (which the Clone never sees), each Signal, the Verdict and the Voice
// Pause. Same voice, different Verdict.

const SHOWN = new Set(["agent_said", "caller_said", "challenge_issued", "verdict", "security_alert_sent", "call_closed"]);

type Step = { label: string; detail: string; state: "todo" | "ok" | "caught" };

/** What the verifier has done so far, in the order an attack meets it. `caught` is a check the Clone failed. */
function steps(call: CallView | null, calls: CallView[]): Step[] {
  const whisper = call?.evidence.find((e) => e.kind === "whisper_phrase")?.signals;
  const code = call?.evidence.find((e) => e.kind === "possession_code")?.signals;
  const codeSent = !!call?.challenges.some((c) => c.kind === "possession_code");
  const blocked = call?.verdict === "BLOCK";
  const refused = !!call && calls.some((c) => c.created_at > call.created_at && isVoicePauseRefusal(c));
  // Caught as played in digitally only when the Policy said so (live_microphone is off until it is safe).
  const injected = !!call && noLiveMic(call) && whisper?.dynamic_range_db != null && whisper.dynamic_range_db > T.micMaxDb;
  const whisperOk = whisper && !injected && (whisper.task_match ?? 0) >= T.task && (whisper.whisper_score ?? 0) >= T.whisper;
  return [
    {
      label: "The Clone says the Request",
      detail: call?.request ? "in the victim's own voice" : "waiting for a Call",
      state: call?.request ? "ok" : "todo",
    },
    {
      label: "The Clone whispers the phrase",
      detail: !whisper
        ? "waiting"
        : injected
          ? `caught: it sounds whispered (score ${whisper.whisper_score?.toFixed(2)}), but there is no room noise around the words (${whisper.dynamic_range_db?.toFixed(0)} dB): played in digitally, not spoken into a microphone`
          : whisperOk
            ? `passes the whisper check (match ${whisper.task_match?.toFixed(2)}, score ${whisper.whisper_score?.toFixed(2)})`
            : "did not match, or was not whispered",
      state: !whisper ? "todo" : whisperOk ? "ok" : "caught",
    },
    {
      label: "A one-time code goes to the real phone",
      detail: codeSent ? "shown only in the Bank App, on the right" : "waiting",
      state: codeSent ? "ok" : "todo",
    },
    {
      label: "The Clone has no code to read",
      detail: !codeSent ? "waiting" : code?.code_match === true ? "a right code was read" : "no right code: the Clone is not holding the phone",
      state: !codeSent ? "todo" : code?.code_match === true ? "ok" : "caught",
    },
    {
      label: "Verdict",
      detail: call?.verdict ? `${call.verdict}${call.liveness != null ? ` · liveness ${call.liveness.toFixed(2)}` : ""}` : "waiting",
      state: !call?.verdict ? "todo" : blocked ? "caught" : "ok",
    },
    {
      label: "Security Alert on the real phone",
      detail: blocked ? "the victim is warned at once" : "only after a BLOCK",
      state: blocked ? "caught" : "todo",
    },
    {
      label: "Calling straight back is refused",
      detail: refused ? "Voice Pause: the Clone cannot just try again" : blocked ? "call again to see it" : "only after a BLOCK",
      state: refused ? "caught" : "todo",
    },
  ];
}

function Conversation({ lines, live }: { lines: TranscriptLine[]; live: boolean }) {
  const shown = lines.filter((l) => SHOWN.has(l.event) && l.text);
  return (
    <ol aria-live="polite" className="flex max-h-[28rem] flex-col gap-2 overflow-y-auto pr-1">
      {shown.length === 0 && <li className="text-sm text-ink-soft">{live ? "Listening…" : "No Call yet. Press Call on the Caller tab."}</li>}
      {shown.map((l) => {
        const agent = l.speaker === "agent";
        const system = l.speaker === "system";
        return (
          <li
            key={l.seq}
            className={`max-w-[92%] rounded-xl px-3 py-2 text-sm ${
              system
                ? "self-center bg-sunken text-xs text-ink-soft"
                : agent
                  ? "self-start bg-sunken"
                  : "self-end bg-accent/12 text-ink"
            }`}
          >
            {!system && (
              <span className="mb-0.5 block text-[0.7rem] font-semibold uppercase tracking-wide text-ink-soft">
                {agent ? "Voice Agent" : "The Clone (synthetic)"}
              </span>
            )}
            {l.text}
          </li>
        );
      })}
    </ol>
  );
}

export default function DeepfakePage() {
  const [keyVersion, setKeyVersion] = useState(0);
  const [locked, setLocked] = useState(false);
  const { list: calls, connected } = useLiveCalls(keyVersion, () => setLocked(true));
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  const [victimId, setVictimId] = useState("cust-rahul");
  const [full, setFull] = useState<CallView | null>(null);

  useEffect(() => {
    api.demoCustomers().then(setCustomers, () => setLocked(true));
  }, [keyVersion]);

  const victim = customers.find((c) => c.id === victimId);
  const mine = useMemo(() => calls.filter((c) => c.customer.id === victimId), [calls, victimId]);
  const call = mine[0] ?? null;

  // The live events carry the Signals; the conversation is the Call's Transcript, fetched when it changes.
  useEffect(() => {
    if (!call) return setFull(null);
    let alive = true;
    api.call(call.id).then((c) => alive && setFull(c), () => {});
    return () => {
      alive = false;
    };
  }, [call?.id, call?.updated_at]);

  if (locked)
    return (
      <KeyGate
        why="The Deepfake view shows a Call's conversation and the victim's Bank App, so it is for bank staff."
        onKey={(key) => {
          setConsoleKey(key);
          setLocked(false);
          setKeyVersion((v) => v + 1);
        }}
      />
    );

  const list = steps(call, calls);
  const first = victim?.name.split(" ")[0] ?? "the victim";

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">Deepfake: same voice, different Verdict</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-soft">
            A consented Clone of {first}'s voice calls the bank. It says the Request in {first}'s voice and even
            whispers the phrase convincingly. It cannot read the one-time code, which appears only on {first}'s real
            phone.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-ink-soft" htmlFor="victim">Victim</label>
          <select
            id="victim"
            value={victimId}
            onChange={(e) => setVictimId(e.target.value)}
            className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm"
          >
            {customers.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${connected ? "bg-accent/12 text-accent" : "bg-block/10 text-block"}`}>
            {connected ? "Live" : "Reconnecting"}
          </span>
        </div>
      </header>

      <VerdictRibbon call={call} name={victim?.name ?? ""} stage={false} connected={connected} />

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr_19rem]">
        <section aria-label="The Call" className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
          <h2 className="flex items-center gap-2 font-semibold"><Robot size={18} aria-hidden /> The Call: both sides</h2>
          <Conversation lines={full?.transcript ?? []} live={!!call && call.state !== "closed"} />
        </section>

        <section aria-label="What the verifier checks" className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
          <h2 className="font-semibold">What the verifier does</h2>
          <ol className="flex flex-col gap-3">
            {list.map((s) => (
              <li key={s.label} className="flex gap-2.5">
                {s.state === "ok" ? (
                  <CheckCircle size={20} weight="fill" className="mt-0.5 shrink-0 text-ink-soft" aria-label="passed" />
                ) : s.state === "caught" ? (
                  <XCircle size={20} weight="fill" className="mt-0.5 shrink-0 text-block" aria-label="caught" />
                ) : (
                  <Circle size={20} className="mt-0.5 shrink-0 text-line-strong" aria-label="waiting" />
                )}
                <div>
                  <p className={`text-sm font-medium ${s.state === "caught" ? "text-block" : ""}`}>{s.label}</p>
                  <p className="text-xs text-ink-soft">{s.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-label={`${first}'s real phone`} className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
          <h2 className="flex items-center gap-2 font-semibold"><DeviceMobile size={18} aria-hidden /> {first}'s real phone</h2>
          {victim ? <BankApp customer={victim.id} device={victim.device_token} embedded /> : <p className="text-sm text-ink-soft">Loading…</p>}
        </section>
      </div>

      <details className="rounded-xl border border-line bg-surface p-4 text-sm">
        <summary className="cursor-pointer font-semibold">How to run the attack (operator, on the attacker laptop)</summary>
        <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-ink-soft">
          <li>Open the Caller tab, choose {first}, set the microphone to <b>CABLE Output (VB-Audio Virtual Cable)</b>, press <b>Call</b>.</li>
          <li>
            In one terminal run <code>attacker\demo_clone.py</code> (with <code>--i-have-consent</code>), then play the lines as the Voice Agent
            asks: <b>1</b> the Request, a typed phrase for the whisper, <b>2</b> at the code prompt.
          </li>
          <li>Watch this page: the code lands on the real phone, the Clone cannot read it, and the Call is blocked.</li>
          <li>Press Call again: it is refused while the Voice Pause lasts. Lift it on the Demo tab before the next run.</li>
        </ol>
      </details>
    </div>
  );
}
