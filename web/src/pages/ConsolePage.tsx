import { type CSSProperties, useEffect, useRef, useState } from "react";
import {
  Broadcast, CheckCircle, Clock, Database as DbIcon, DownloadSimple, Headset, LinkSimple, ListChecks,
  Prohibit, Robot, SealCheck, ShieldCheck, ShieldWarning, Siren, Timer, User, Warning, Waveform,
} from "@phosphor-icons/react";
import { HttpError, api, downloadTranscript, setConsoleKey } from "../api";
import {
  Card, ErrorNote, KeyGate, Meter, OutcomeLabel, REQUEST_ICON, VerdictBadge, scriptLang, useLiveCalls, useStage,
} from "../components";
import type {
  AuditCheck, CallView, CustomerRisk, ReceiptCheck, Signals, Stats, Status, TranscriptLine,
} from "../types";
import { REQUEST_LABEL } from "../types";
import { FACTOR_LABEL, T, decidedBy, headline } from "../verdict";

type Filter = "all" | "live" | "review" | "blocked" | "passed";
const FILTERS: [Filter, string, (c: CallView) => boolean][] = [
  ["all", "All", () => true],
  ["live", "Live", (c) => c.state !== "closed"],
  ["review", "Review", (c) => c.review_status === "pending"],
  ["blocked", "Blocked", (c) => c.outcome === "blocked"],
  ["passed", "Passed", (c) => c.verdict === "PASS"],
];

/** The Console. With ?stage=1 (the projector) it opens the latest decided Call by itself, at 125% type. */
export default function ConsolePage() {
  const stage = useStage();
  const [keyVersion, setKeyVersion] = useState(0);
  const [locked, setLocked] = useState(false);
  const { list, connected, loaded, setCalls } = useLiveCalls(keyVersion, () => setLocked(true));
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const shown = list.filter(FILTERS.find(([f]) => f === filter)![2]);
  // On the projector nobody clicks: follow the newest Call that has a Verdict.
  const latestDecided = list.find((c) => c.verdict !== null);
  const call = list.find((c) => c.id === selected) ?? (stage && latestDecided ? latestDecided : shown[0]);

  function unlock(key: string) {
    setConsoleKey(key);
    setLocked(false);
    setKeyVersion((v) => v + 1);
  }

  if (locked) return <KeyGate onKey={unlock} />;

  return (
    <div className="flex flex-col gap-6">
      <StatusBar />
      <div className="grid gap-6 lg:grid-cols-[21rem_1fr]">
        <Card
          title={
            <span className="flex items-center justify-between">
              Calls
              {connected ? (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-accent">
                  <span className="live-dot" aria-hidden /> Live
                </span>
              ) : (
                <span className="text-xs font-medium text-block">Reconnecting</span>
              )}
            </span>
          }
        >
          <div className="mb-3 flex flex-wrap gap-1" role="tablist" aria-label="Filter Calls">
            {FILTERS.map(([f, label, pred]) => {
              const n = list.filter(pred).length;
              return (
                <button
                  key={f}
                  role="tab"
                  aria-selected={filter === f}
                  onClick={() => setFilter(f)}
                  className={`press rounded-full px-2.5 py-1 text-xs font-medium ${
                    filter === f ? "bg-accent text-on-accent" : "bg-sunken text-ink-soft hover:text-ink"
                  }`}
                >
                  {label} <span className="font-mono opacity-75">{n}</span>
                </button>
              );
            })}
          </div>
          {!loaded && (
            <div className="flex flex-col gap-2" aria-busy="true">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton h-14" />)}
            </div>
          )}
          {loaded && shown.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-ink-soft">
              <Headset size={28} />
              {list.length === 0 ? "No calls yet. Place one from the Caller tab." : "No calls match this filter."}
            </div>
          )}
          <ul className="flex flex-col gap-1">
            {shown.map((c, i) => {
              const Glyph = c.request ? REQUEST_ICON[c.request] : Waveform;
              return (
                <li key={c.id} className="motion-enter" style={{ "--i": i } as CSSProperties}>
                  <button
                    onClick={() => setSelected(c.id)}
                    className={`press flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left ${
                      call?.id === c.id ? "bg-accent/10 ring-1 ring-accent/30" : "hover:bg-sunken"} ${c.verdict === "BLOCK" ? "border-l-2 border-block" : ""
                    }`}
                  >
                    <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${c.state === "closed" ? "bg-sunken text-ink-soft" : "bg-accent/12 text-accent"}`}>
                      <Glyph size={17} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate font-semibold">{c.customer.name}</span>
                        <VerdictBadge verdict={c.verdict} />
                      </span>
                      <span className="flex items-center justify-between gap-2 text-xs text-ink-soft">
                        <span className="truncate">{c.request ? REQUEST_LABEL[c.request] : "listening…"}</span>
                        <span className="shrink-0 whitespace-nowrap font-mono">{new Date(c.created_at + "Z").toLocaleTimeString()}</span>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>
        {call ? (
          <CallDetail key={call.id} call={call} onUpdate={(c) => setCalls((p) => ({ ...p, [c.id]: c }))} onLocked={() => setLocked(true)} />
        ) : (
          <div />
        )}
      </div>
    </div>
  );
}

/** Is the setup ready (GET /v1/status), live numbers, and whether an Attack Wave is on (GET /v1/stats). */
function StatusBar() {
  const [status, setStatus] = useState<Status | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = () => {
      api.status().then((s) => alive && setStatus(s)).catch(() => alive && setStatus(null));
      api.stats().then((s) => alive && setStats(s)).catch(() => undefined);
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  const passed = (stats?.by_outcome.passed ?? 0) + (stats?.by_outcome.passed_pending_review ?? 0);
  const wave = stats?.attack_wave;
  return (
    <div className="flex flex-col gap-2">
      {wave?.active && (
        <div className="motion-enter flex flex-wrap items-center gap-3 rounded-xl border border-block/40 bg-block/10 px-4 py-3 text-sm" role="alert">
          <Siren size={22} className="text-block" />
          <b className="text-block">Attack Wave</b>
          <span>
            Blocked Calls for {wave.customers} Customers in the last {wave.minutes} min. Every risky Request now also needs
            Agent Review.
          </span>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${
            !status ? "bg-block/10 text-block ring-block/30"
            : status.ready ? "bg-pass/10 text-pass ring-pass/30" : "bg-stepup/10 text-stepup ring-stepup/30"
          }`}
        >
          {status?.ready ? <CheckCircle size={14} weight="bold" /> : <Warning size={14} weight="bold" />}
          {status ? (status.ready ? "Ready" : "Not ready") : "Verifier unreachable"}
        </span>
        {stats && (
          <>
            <span><b>{stats.calls}</b> Calls</span>
            <span className="text-pass"><b>{passed}</b> passed</span>
            <span className="text-block"><b>{stats.blocked}</b> blocked</span>
            <span className="inline-flex items-center gap-1"><Clock size={15} className="text-ink-soft" /> Added Time <b>{stats.avg_added_seconds === null ? "-" : `${stats.avg_added_seconds.toFixed(1)} s`}</b></span>
            <span className="inline-flex items-center gap-1" title="Time to hear a Response: speech models and understanding">
              <Timer size={15} className="text-ink-soft" /> Hearing <b>{stats.hearing_ms.p50 ?? "-"}</b>
              <span className="text-ink-soft">/ p95 {stats.hearing_ms.p95 ?? "-"} ms</span>
            </span>
            {wave && !wave.active && wave.blocked > 0 && (
              <span className="inline-flex items-center gap-1 text-ink-soft">
                <Broadcast size={15} /> {wave.customers}/{wave.threshold} Customers blocked in {wave.minutes} min
              </span>
            )}
          </>
        )}
        {status && (
          <span className="ml-auto flex flex-wrap gap-4 text-xs text-ink-soft">
            <span className="inline-flex items-center gap-1"><DbIcon size={14} /> {status.database.dialect}</span>
            <span className="inline-flex items-center gap-1"><Waveform size={14} /> {status.speech.backend} {status.speech.whisper_model}</span>
            <span className="inline-flex items-center gap-1"><Robot size={14} /> LLM {status.llm.model ?? "off"}</span>
          </span>
        )}
      </div>
      {status && status.warnings.length > 0 && (
        <ul className="motion-enter list-disc rounded-xl border border-stepup/25 bg-stepup/[0.06] px-8 py-2 text-sm">
          {status.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
    </div>
  );
}

function AuditBadge({ audit }: { audit?: AuditCheck }) {
  if (!audit) return null;
  return audit.intact ? (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <b className="inline-flex items-center gap-1.5 text-pass"><LinkSimple size={16} weight="bold" /> Audit Trail intact</b>
      <span className="text-ink-soft">{audit.events} events, hash-chained</span>
      <span className="font-mono text-xs text-ink-soft">head {audit.head?.slice(0, 12)}…</span>
    </p>
  ) : (
    <p className="motion-pop inline-flex items-center gap-1.5 text-sm font-bold text-block">
      <ShieldWarning size={18} weight="bold" /> Audit Trail altered at event #{audit.broken_at}
    </p>
  );
}

/** What a fraud officer wants to know about the Customer now (GET /v1/customers/{id}/risk). */
function RiskPanel({ customerId, refresh }: { customerId: string; refresh: string }) {
  const [risk, setRisk] = useState<CustomerRisk | null>(null);
  useEffect(() => {
    let current = true;
    api.customerRisk(customerId).then((r) => current && setRisk(r)).catch(() => undefined);
    return () => {
      current = false;
    };
  }, [customerId, refresh]);
  if (!risk) return <div className="skeleton h-10" />;
  const style = { high: "bg-block/10 text-block ring-block/30", elevated: "bg-stepup/10 text-stepup ring-stepup/30", normal: "bg-pass/10 text-pass ring-pass/30" }[risk.risk];
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg bg-sunken px-3 py-2.5 text-sm">
      <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide ring-1 ${style}`}>{risk.risk} risk</span>
      <span className="text-ink-soft">{risk.customer.phone_masked}</span>
      <span><b>{risk.calls_7d}</b> Calls in 7 days{risk.blocked_24h > 0 && <>, <b className="text-block">{risk.blocked_24h} blocked</b> today</>}</span>
      {risk.open_security_alerts > 0 && (
        <span className="inline-flex items-center gap-1 text-block"><Siren size={15} /> {risk.open_security_alerts} open Security Alert</span>
      )}
      {risk.voice_pause.active && (
        <span className="inline-flex items-center gap-1 font-medium text-block">
          <Timer size={15} /> Voice Pause, {Math.ceil(risk.voice_pause.minutes_left ?? 0)} min left
        </span>
      )}
    </div>
  );
}

/** Issue the signed Verification Receipt core banking would check, check it, and redeem it once. */
function ReceiptPanel({ callId, onLocked }: { callId: string; onLocked: () => void }) {
  const [check, setCheck] = useState<ReceiptCheck | null>(null);
  const [token, setToken] = useState("");
  const [redeemed, setRedeemed] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown) => (e instanceof HttpError && e.status === 403 ? onLocked() : setError(String(e)));
  async function issue() {
    try {
      const r = await api.receipt(callId);
      setToken(r.receipt);
      setCheck(await api.verifyReceipt(r.receipt));
      setError(null);
    } catch (e) {
      fail(e);
    }
  }
  async function redeem() {
    try {
      await api.redeemReceipt(token);
      setRedeemed("Redeemed: core banking carried out the Request. A second redeem is refused.");
      setCheck(await api.verifyReceipt(token));
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) setRedeemed(e.message.replace(/^409: /, ""));
      else fail(e);
    }
  }
  const c = check?.claims;
  return (
    <div className="rounded-lg bg-sunken p-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center gap-1.5 font-semibold"><SealCheck size={17} className="text-accent" /> Verification Receipt</span>
        <span className="ml-auto flex gap-2">
          {check?.valid && c?.executable && !check.redeemed && (
            <button className="press rounded-lg bg-surface px-3 py-1.5 text-sm font-semibold ring-1 ring-line hover:ring-accent/50" onClick={redeem}>
              Redeem as core banking
            </button>
          )}
          <button className="press rounded-lg bg-accent px-3 py-1.5 text-sm font-bold text-on-accent" onClick={issue}>
            {check ? "Issue again" : "Issue & verify"}
          </button>
        </span>
      </div>
      {check && (
        <p className="motion-enter mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {check.valid ? <b className="text-pass">Signature valid (Ed25519)</b> : <b className="text-block">Invalid: {check.reason}</b>}
          {c && (
            <>
              <span>Core banking may act: <b className={c.executable ? "text-pass" : "text-block"}>{c.executable ? "yes" : "no"}</b></span>
              {check.redeemed && <span className="font-semibold text-ink">already redeemed</span>}
              <span className="text-ink-soft">Expires {new Date(c.exp * 1000).toLocaleTimeString()}</span>
            </>
          )}
        </p>
      )}
      {redeemed && <p className="motion-enter mt-1 text-sm font-medium">{redeemed}</p>}
      {token && <p className="mt-1 break-all font-mono text-[0.65rem] text-ink-soft">{token.slice(0, 120)}…</p>}
      <ErrorNote error={error} />
    </div>
  );
}

type Tab = "transcript" | "evidence" | "audit";

function CallDetail({ call, onUpdate, onLocked }: { call: CallView; onUpdate: (c: CallView) => void; onLocked: () => void }) {
  const [tab, setTab] = useState<Tab>("transcript");
  const [full, setFull] = useState<CallView | null>(call.events ? call : null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (call.events) {
      setFull(call);
      return;
    }
    let current = true; // ignore a slow reply for a Call that is no longer selected
    api
      .call(call.id)
      .then((c) => current && setFull(c))
      .catch((e) => current && e instanceof HttpError && e.status === 403 && onLocked());
    return () => {
      current = false;
    };
  }, [call.id, call.updated_at, call.events]);

  async function review(approve: boolean) {
    try {
      onUpdate(await api.review(call.id, approve));
      setError(null);
    } catch (e) {
      if (e instanceof HttpError && e.status === 403) onLocked();
      else setError(String(e));
    }
  }

  const Glyph = call.request ? REQUEST_ICON[call.request] : Waveform;
  const tabs: [Tab, string, typeof ListChecks][] = [
    ["transcript", "Transcript", Headset],
    ["evidence", "Challenges & Signals", Waveform],
    ["audit", "Audit Trail", LinkSimple],
  ];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div>
            <p className="text-xs font-medium text-ink-soft">Caller claims to be</p>
            <p className="font-display text-2xl font-semibold tracking-tight">{call.customer.name}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-ink-soft">Request</p>
            <p className="inline-flex items-center gap-1.5 font-semibold">
              <Glyph size={17} className="text-accent" /> {call.request ? REQUEST_LABEL[call.request] : "-"}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-ink-soft">Liveness</p>
            <p className="font-display text-2xl font-semibold tabular-nums">{call.liveness?.toFixed(2) ?? "-"}</p>
          </div>
          <div className="ml-auto flex flex-col items-end gap-1">
            <VerdictBadge verdict={call.verdict} large />
            <OutcomeLabel outcome={call.outcome} />
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3">
          <Conclusion call={call} />
          <RiskPanel customerId={call.customer.id} refresh={call.updated_at} />
          {call.reasons.length > 0 && (
            <ul className="motion-enter list-disc space-y-1 pl-5 text-sm">
              {call.reasons.map((r, i) => (
                <li key={i} className={i === 0 ? "font-semibold" : ""}>{r}</li>
              ))}
            </ul>
          )}
          {call.review_status === "pending" && (
            <div className="motion-enter flex flex-wrap items-center gap-3 rounded-lg border border-stepup/30 bg-stepup/10 p-3">
              <User size={20} className="text-stepup" />
              <span className="text-sm font-semibold">Agent Review: a bank officer must confirm this Request.</span>
              <span className="ml-auto flex gap-2">
                <button className="press rounded-lg bg-surface px-3 py-1.5 text-sm font-bold text-block ring-1 ring-block/40" onClick={() => review(false)}>
                  Reject
                </button>
                <button className="press rounded-lg bg-accent px-3 py-1.5 text-sm font-bold text-on-accent" onClick={() => review(true)}>
                  Approve
                </button>
              </span>
            </div>
          )}
          {call.review_status && call.review_status !== "pending" && (
            <p className="text-sm">Agent Review: <b>{call.review_status}</b></p>
          )}
          <AuditBadge audit={full?.audit} />
          {call.state === "closed" && <ReceiptPanel key={call.id} callId={call.id} onLocked={onLocked} />}
          <ErrorNote error={error} />
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        {tabs.map(([t, label, Icon]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`press inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold ${
              tab === t ? "bg-accent/12 text-accent" : "text-ink-soft hover:bg-sunken hover:text-ink"
            }`}
          >
            <Icon size={16} /> {label}
          </button>
        ))}
        {tab === "transcript" && (
          <button
            className="press ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-ink-soft ring-1 ring-line hover:text-ink"
            onClick={() => downloadTranscript(call.id).catch((e) => setError(String(e)))}
          >
            <DownloadSimple size={16} /> Download .txt
          </button>
        )}
      </div>

      {tab === "transcript" && <TranscriptView lines={full?.transcript} live={call.state !== "closed"} />}
      {tab === "evidence" && (
        <div className="grid gap-4 xl:grid-cols-2">
          {call.challenges.length === 0 && <p className="text-sm text-ink-soft">No Challenges yet.</p>}
          {call.challenges.map((ch, i) => {
            const ev = call.evidence[i];
            return (
              <Card
                key={i}
                className="motion-enter"
                title={
                  <span className="flex items-center justify-between">
                    <span>{i + 1}. {ch.kind === "whisper_phrase" ? "Whisper Phrase" : "Possession Code"}</span>
                    {call.scores[i] !== undefined && <span className="font-mono normal-case">liveness {call.scores[i].toFixed(2)}</span>}
                  </span>
                }
              >
                {ch.phrase && (
                  <p className="mb-2 text-sm">
                    expected: <span className="font-medium" lang={scriptLang(ch.phrase)}>“{ch.phrase}”</span>
                  </p>
                )}
                {ev ? (
                  <SignalView kind={ch.kind} s={ev.signals} />
                ) : (
                  <div className="flex flex-col gap-2.5" aria-busy="true">
                    <p className="text-sm text-accent">Waiting for the Caller…</p>
                    {[0, 1, 2].map((k) => <div key={k} className="skeleton h-2" />)}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
      {tab === "audit" && (
        <Card>
          <ol className="flex flex-col gap-2 font-mono text-xs">
            {(full?.events ?? []).map((e) => (
              <li key={e.seq} className="grid grid-cols-[2.5rem_6rem_10rem_1fr] gap-2 border-b border-line pb-2 last:border-b-0">
                <span className="text-ink-soft">#{e.seq}</span>
                <span className="text-ink-soft">{new Date(e.at + "Z").toLocaleTimeString()}</span>
                <span className="font-semibold">{e.kind}</span>
                <span className="break-all text-ink-soft">{JSON.stringify(e.data)}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}

const LANGUAGE = { en: "English", hi: "हिन्दी", kn: "ಕನ್ನಡ" } as const;
const UNDERSTOOD: Record<string, string> = {
  request: "Request",
  question: "Question",
  chat: "Small talk",
  repeat: "Asked to repeat",
  wait: "Asked to wait",
  app_approval: "Wants the app",
  human: "Wants a person",
  goodbye: "Goodbye",
  unclear: "Unclear",
};
const TONE_TEXT = { pass: "text-pass", stepup: "text-stepup", block: "text-block" } as const;

/** The Call as a conversation: the Voice Agent on the left, the Caller on the right, the Verifier's
 *  steps between them. Follows new lines while the Call is live, unless the operator scrolled up. */
function TranscriptView({ lines, live }: { lines?: TranscriptLine[]; live: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  useEffect(() => {
    const el = box.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [lines?.length]);
  if (!lines)
    return (
      <Card>
        <div className="flex flex-col gap-3" aria-busy="true">
          {[0, 1, 2].map((k) => <div key={k} className={`skeleton h-10 ${k % 2 ? "ml-auto w-2/3" : "w-3/4"}`} />)}
        </div>
      </Card>
    );
  const spoken = lines.filter((l) => l.speaker !== "system");
  const last = spoken[spoken.length - 1];
  return (
    <section className="rounded-xl border border-line bg-surface">
      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        className="flex max-h-[36rem] flex-col gap-3 overflow-y-auto p-4"
        aria-live="polite"
      >
        {lines.map((l, i) => <Line key={l.seq} line={l} i={i} />)}
        {live && (
          <div className={`flex items-center gap-2 text-xs text-ink-soft ${last?.speaker === "agent" ? "ml-auto" : ""}`}>
            <span className="typing inline-flex gap-1 text-accent" aria-hidden><span /><span /><span /></span>
            {last?.speaker === "agent" ? "Waiting for the Caller" : "The Voice Agent is thinking"}
          </div>
        )}
      </div>
    </section>
  );
}

function Line({ line: l, i }: { line: TranscriptLine; i: number }) {
  const time = new Date(l.at + "Z").toLocaleTimeString();
  const style = { "--i": Math.min(i, 3) } as CSSProperties;
  if (l.speaker === "system") {
    const toned = l.tone ? TONE_TEXT[l.tone] : "text-ink-soft";
    return (
      <div className={`motion-enter flex items-center gap-3 text-xs ${toned}`} style={style}>
        <span className="h-px flex-1 bg-line" />
        <span className={`max-w-[80%] text-center ${l.event === "verdict" ? "font-semibold" : ""}`} lang={scriptLang(l.text)}>{l.text}</span>
        <span className="h-px flex-1 bg-line" />
      </div>
    );
  }
  if (l.speaker === "agent") {
    return (
      <div className="motion-enter flex max-w-[85%] items-start gap-2.5" style={style}>
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent/12 text-accent" aria-hidden>
          <Waveform size={17} />
        </span>
        <div className="min-w-0">
          <p className="mb-1 text-xs text-ink-soft">Voice Agent · <span className="font-mono">{time}</span></p>
          <p className="rounded-2xl rounded-tl-sm bg-sunken px-3.5 py-2 leading-relaxed" lang={scriptLang(l.text)}>{l.text}</p>
        </div>
      </div>
    );
  }
  const s = l.signals ?? {};
  const chips: [string, string][] = [];
  if (l.language) chips.push([LANGUAGE[l.language], ""]);
  if (l.understood) chips.push([UNDERSTOOD[l.understood] ?? l.understood, ""]);
  if (l.by_llm) chips.push(["understood by the LLM", "text-accent"]);
  if (l.by_variant) chips.push(["understood from a misheard word", "text-accent"]);
  if (l.liveness != null) chips.push([`liveness ${l.liveness.toFixed(2)}`, l.liveness >= 0.75 ? "text-pass" : l.liveness <= 0.45 ? "text-block" : "text-stepup"]);
  if (s.task_match != null) chips.push([`task ${s.task_match.toFixed(2)}`, s.task_match >= T.task ? "" : "text-block"]);
  if (s.whisper_score != null) chips.push([`whisper ${s.whisper_score.toFixed(2)}`, s.whisper_score >= T.whisper ? "" : "text-block"]);
  if (s.reply_latency_ms != null) chips.push([`${s.reply_latency_ms} ms reply`, s.reply_latency_ms <= T.humanMs ? "" : "text-stepup"]);
  if (s.spoof_score != null) chips.push([`spoof ${s.spoof_score.toFixed(2)} (advisory)`, ""]);
  if (s.code_match != null) chips.push([s.code_match ? "code matches" : "code wrong", s.code_match ? "text-pass" : "text-block"]);
  return (
    <div className="motion-enter ml-auto flex max-w-[85%] flex-row-reverse items-start gap-2.5" style={style}>
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-sunken text-ink-soft" aria-hidden>
        <User size={17} />
      </span>
      <div className="flex min-w-0 flex-col items-end">
        <p className="mb-1 text-xs text-ink-soft">
          {l.timings_ms?.total != null && <span className="font-mono">heard in {l.timings_ms.total} ms · </span>}
          Caller · <span className="font-mono">{time}</span>
        </p>
        <p className="rounded-2xl rounded-tr-sm bg-accent/12 px-3.5 py-2 leading-relaxed ring-1 ring-accent/20" lang={l.language === "en" ? undefined : scriptLang(l.text)}>
          {l.text || <span className="italic text-ink-soft">silence</span>}
        </p>
        {l.note && <p className="mt-1 text-xs font-medium text-stepup">{l.note}</p>}
        {chips.length > 0 && (
          <p className="mt-1.5 flex flex-wrap justify-end gap-1">
            {chips.map(([text, cls]) => (
              <span key={text} lang={scriptLang(text)} className={`rounded-full bg-sunken px-2 py-0.5 font-mono text-[0.68rem] ${cls || "text-ink-soft"}`}>{text}</span>
            ))}
          </p>
        )}
      </div>
    </div>
  );
}

/** The top of a decided Call, read in three seconds: the Verdict word, one plain sentence, what decided it,
 *  and the authentication factors it rests on (Datadog's order: conclusion, then evidence). */
function Conclusion({ call }: { call: CallView }) {
  if (!call.verdict) return null;
  const by = decidedBy(call);
  const word = { PASS: "PASS", STEP_UP: "STEP-UP", BLOCK: "BLOCKED" }[call.verdict];
  const tone = { PASS: "text-pass", STEP_UP: "text-stepup", BLOCK: "text-block" }[call.verdict];
  const edge = { PASS: "border-pass", STEP_UP: "border-stepup", BLOCK: "border-block" }[call.verdict];
  const Glyph = { PASS: ShieldCheck, STEP_UP: Warning, BLOCK: Prohibit }[call.verdict];
  const code = call.evidence.find((e) => e.kind === "possession_code")?.signals.code_match;
  const whisper = call.evidence.filter((e) => e.kind === "whisper_phrase").at(-1)?.signals;
  const factors: [string, boolean | null][] = [
    ["Possession (Registered Device)", code === undefined ? null : !!code],
    ["Inherence, liveness (Whisper)", whisper ? (whisper.whisper_score ?? 0) >= T.whisper && (whisper.task_match ?? 0) >= T.task : null],
  ];
  return (
    <div className={`motion-enter flex flex-col gap-2 border-l-2 pl-4 ${edge}`}>
      <p className={`flex items-center gap-2 font-display text-3xl font-bold tracking-tight ${tone}`}>
        <Glyph size={30} weight="fill" aria-hidden /> {word}
      </p>
      <p className="text-lg font-medium leading-snug">{headline(call, call.customer.name.split(" ")[0])}</p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        {by && (
          <span className="rounded-full bg-sunken px-3 py-1">
            Decided by: <b>{FACTOR_LABEL[by]}</b>
          </span>
        )}
        {factors.map(([name, ok]) => (
          <span key={name} className="inline-flex items-center gap-1 text-ink-soft">
            {ok === null ? "not asked" : ok ? <CheckCircle size={15} weight="fill" className="text-ink" /> : <Prohibit size={15} weight="fill" className="text-block" />}
            {name}
          </span>
        ))}
        <span className="text-xs text-ink-soft">Aligned to RBI Authentication Directions 2025</span>
      </div>
    </div>
  );
}

function SignalView({ kind, s }: { kind: string; s: Signals }) {
  const latency = s.reply_latency_ms;
  const latencyScore =
    latency === null ? null : Math.max(0, Math.min(1, 1 - (latency - T.humanMs) / (T.machineMs - T.humanMs)));
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm">
        heard: <span className="font-medium" lang={scriptLang(s.transcript)}>“{s.transcript || "…"}”</span>
      </p>
      {kind === "whisper_phrase" && <Meter label="Task Match" value={s.task_match} threshold={T.task} />}
      {kind === "whisper_phrase" && <Meter label="Whisper Score" value={s.whisper_score} threshold={T.whisper} />}
      {/* full credit only at or under human_ms, matching the Policy's "slow reply" Reason */}
      {kind === "whisper_phrase" && (
        <Meter label="Reply Latency" value={latencyScore} threshold={1} missed="slow" suffix={latency === null ? "none" : `${latency} ms`} />
      )}
      <Meter label="Spoof Score" value={s.spoof_score} advisory />
      {kind === "possession_code" && (
        <p className="text-sm">
          code read out: <span className="font-mono">{s.spoken_digits ?? "-"}</span>{" "}
          {s.code_match === true && <b className="text-pass">matches the device</b>}
          {s.code_match === false && <b className="text-block">does not match</b>}
        </p>
      )}
    </div>
  );
}
