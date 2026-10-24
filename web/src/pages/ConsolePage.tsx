import { type CSSProperties, useEffect, useMemo, useState } from "react";
import { api, eventsUrl } from "../api";
import { Card, ErrorNote, Meter, OutcomeLabel, VerdictBadge } from "../components";
import type { AuditCheck, CallView, ReceiptCheck, Signals, Stats, Status } from "../types";
import { REQUEST_LABEL } from "../types";

// Mirrors the defaults in policy.yaml, for drawing threshold marks only.
const T = { task: 0.7, whisper: 0.6, humanMs: 1200, machineMs: 3000, spoof: 0.85 };

function useLiveCalls() {
  const [calls, setCalls] = useState<Record<string, CallView>>({});
  const [connected, setConnected] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const connect = () => {
      ws = new WebSocket(eventsUrl());
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "snapshot") {
          setCalls(Object.fromEntries((msg.calls as CallView[]).map((c) => [c.id, c])));
          setLoaded(true);
        } else if (msg.type === "call") {
          const c = msg.call as CallView;
          // Updates can arrive out of order across server threads; keep the newest.
          setCalls((prev) => (prev[c.id] && prev[c.id].updated_at > c.updated_at ? prev : { ...prev, [c.id]: c }));
        }
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, []);

  const list = useMemo(
    () => Object.values(calls).sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [calls],
  );
  return { list, connected, loaded, setCalls };
}

export default function ConsolePage() {
  const { list, connected, loaded, setCalls } = useLiveCalls();
  const [selected, setSelected] = useState<string | null>(null);
  const call = list.find((c) => c.id === selected) ?? list[0];

  return (
    <div className="flex flex-col gap-6">
      <StatusBar />
      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <Card
          title={
            <span className="flex items-center justify-between">
              Calls
              {connected ? (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-pass">
                  <span className="live-dot" aria-hidden /> Live
                </span>
              ) : (
                <span className="text-xs font-medium text-block">Reconnecting</span>
              )}
            </span>
          }
        >
          {!loaded && (
            <div className="flex flex-col gap-2" aria-busy="true">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton h-12" />)}
            </div>
          )}
          {loaded && list.length === 0 && <p className="text-sm text-ink-soft">No calls yet. Place one from the Caller tab.</p>}
          <ul className="flex flex-col gap-1">
            {list.map((c, i) => (
              <li key={c.id} className="motion-enter" style={{ "--i": i } as CSSProperties}>
                <button
                  onClick={() => setSelected(c.id)}
                  className={`press w-full rounded-lg px-3 py-2 text-left ${
                    call?.id === c.id ? "bg-accent/10 ring-1 ring-accent/30" : "hover:bg-sunken"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{c.customer.name}</span>
                    <VerdictBadge verdict={c.verdict} />
                  </div>
                  <div className="flex items-center justify-between text-xs text-ink-soft">
                    <span>{c.request ? REQUEST_LABEL[c.request] : "listening…"}</span>
                    <span>{new Date(c.created_at + "Z").toLocaleTimeString()}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </Card>
        {call ? <CallDetail call={call} onUpdate={(c) => setCalls((p) => ({ ...p, [c.id]: c }))} /> : <div />}
      </div>
    </div>
  );
}

/** Is the setup ready (GET /v1/status), and live numbers (GET /v1/stats). */
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
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${
            !status ? "bg-block/10 text-block ring-block/30"
            : status.ready ? "bg-pass/10 text-pass ring-pass/30" : "bg-stepup/10 text-stepup ring-stepup/30"
          }`}
        >
          {status ? (status.ready ? "Ready" : "Not ready") : "Verifier unreachable"}
        </span>
        {stats && (
          <>
            <span><b>{stats.calls}</b> Calls</span>
            <span className="text-pass"><b>{passed}</b> passed</span>
            <span className="text-block"><b>{stats.blocked}</b> blocked</span>
            <span>Added Time <b>{stats.avg_added_seconds === null ? "-" : `${stats.avg_added_seconds.toFixed(1)} s`}</b></span>
          </>
        )}
        {status && (
          <span className="ml-auto flex gap-4 text-xs text-ink-soft">
            <span>{status.database.dialect}</span>
            <span>{status.speech.backend} {status.speech.whisper_model}</span>
            <span>LLM {status.llm.model ?? "off"}</span>
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
    <p className="mt-3 text-sm">
      <b className="text-pass">Audit Trail intact</b>{" "}
      <span className="ml-2 text-ink-soft">{audit.events} events, hash-chained</span>
      <span className="ml-3 font-mono text-xs text-ink-soft">head {audit.head?.slice(0, 12)}…</span>
    </p>
  ) : (
    <p className="motion-pop mt-3 text-sm font-bold text-block">Audit Trail altered at event #{audit.broken_at}</p>
  );
}

/** Fetch the signed Verification Receipt core banking would check, and check it. */
function ReceiptPanel({ callId, consoleKey, onKey }: { callId: string; consoleKey: string; onKey: (k: string) => void }) {
  const [check, setCheck] = useState<ReceiptCheck | null>(null);
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setCheck(null);
    setToken("");
    setError(null);
  }, [callId]);
  async function fetchReceipt() {
    try {
      const r = await api.receipt(callId, consoleKey);
      setToken(r.receipt);
      setCheck(await api.verifyReceipt(r.receipt));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }
  const c = check?.claims;
  return (
    <div className="mt-4 rounded-lg bg-sunken p-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-semibold">Verification Receipt</span>
        <input
          type="password"
          placeholder="console key"
          aria-label="Console key"
          className="ml-auto w-36 rounded-lg border border-line bg-surface px-2 py-1 text-sm"
          value={consoleKey}
          onChange={(e) => onKey(e.target.value)}
        />
        <button className="press rounded-lg bg-accent px-3 py-1.5 text-sm font-bold text-on-color" onClick={fetchReceipt}>
          {check ? "Refresh" : "Issue & verify"}
        </button>
      </div>
      {check && (
        <p className="motion-enter mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {check.valid ? <b className="text-pass">Signature valid (Ed25519)</b> : <b className="text-block">Invalid: {check.reason}</b>}
          {c && (
            <>
              <span>Core banking may act: <b className={c.executable ? "text-pass" : "text-block"}>{c.executable ? "yes" : "no"}</b></span>
              <span className="text-ink-soft">Expires {new Date(c.exp * 1000).toLocaleTimeString()}</span>
            </>
          )}
        </p>
      )}
      {token && <p className="mt-1 break-all font-mono text-[0.65rem] text-ink-soft">{token.slice(0, 120)}…</p>}
      <ErrorNote error={error} />
    </div>
  );
}

function CallDetail({ call, onUpdate }: { call: CallView; onUpdate: (c: CallView) => void }) {
  const [tab, setTab] = useState<"evidence" | "audit">("evidence");
  const [events, setEvents] = useState(call.events ?? []);
  const [audit, setAudit] = useState(call.audit);
  const [error, setError] = useState<string | null>(null);

  const [consoleKey, setConsoleKey] = useState(() => {
    try {
      return sessionStorage.getItem("consoleKey") ?? "";
    } catch {
      return "";
    }
  });

  useEffect(() => {
    if (call.events) {
      setEvents(call.events);
      setAudit(call.audit);
      return;
    }
    let current = true; // ignore a slow reply for a Call that is no longer selected
    api
      .call(call.id)
      .then((c) => {
        if (!current) return;
        setEvents(c.events ?? []);
        setAudit(c.audit);
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [call.id, call.updated_at, call.events]);

  async function review(approve: boolean) {
    try {
      onUpdate(await api.review(call.id, approve, consoleKey));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  function saveKey(k: string) {
    setConsoleKey(k);
    try {
      sessionStorage.setItem("consoleKey", k);
    } catch {
      /* private mode: keep it in memory */
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div>
            <p className="text-xs font-medium text-ink-soft">Caller claims to be</p>
            <p className="text-xl font-bold">{call.customer.name}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-ink-soft">Request</p>
            <p className="font-semibold">{call.request ? REQUEST_LABEL[call.request] : "-"}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-ink-soft">Liveness</p>
            <p className="font-mono text-xl">{call.liveness?.toFixed(2) ?? "-"}</p>
          </div>
          <div className="ml-auto flex flex-col items-end gap-1">
            <VerdictBadge verdict={call.verdict} />
            <OutcomeLabel outcome={call.outcome} />
          </div>
        </div>
        {call.reasons.length > 0 && (
          <ul className="motion-enter mt-4 list-disc space-y-1 pl-5 text-sm">
            {call.reasons.map((r, i) => (
              <li key={i} className={i === 0 ? "font-semibold" : ""}>{r}</li>
            ))}
          </ul>
        )}
        {call.review_status === "pending" && (
          <div className="motion-enter mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-stepup/30 bg-stepup/10 p-3">
            <span className="text-sm font-semibold">Agent Review needed for this high-value request.</span>
            <input
              type="password"
              placeholder="console key"
              aria-label="Console key"
              className="ml-auto w-36 rounded-lg border border-line bg-surface px-2 py-1 text-sm"
              value={consoleKey}
              onChange={(e) => saveKey(e.target.value)}
            />
            <button className="press rounded-lg bg-surface px-3 py-1.5 text-sm font-bold text-block ring-1 ring-block/40" onClick={() => review(false)}>
              Reject
            </button>
            <button className="press rounded-lg bg-pass px-3 py-1.5 text-sm font-bold text-on-color" onClick={() => review(true)}>
              Approve
            </button>
          </div>
        )}
        {call.review_status && call.review_status !== "pending" && (
          <p className="mt-3 text-sm">Agent Review: <b>{call.review_status}</b></p>
        )}
        <AuditBadge audit={audit} />
        {call.state === "closed" && <ReceiptPanel callId={call.id} consoleKey={consoleKey} onKey={saveKey} />}
        <ErrorNote error={error} />
      </Card>

      <div className="flex gap-2">
        {(["evidence", "audit"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`press rounded-lg px-3 py-1.5 text-sm font-semibold ${
              tab === t ? "bg-accent/10 text-accent" : "text-ink-soft hover:bg-sunken hover:text-ink"
            }`}
          >
            {t === "evidence" ? "Challenges & Signals" : "Audit Trail"}
          </button>
        ))}
      </div>

      {tab === "evidence" ? (
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
                {ch.phrase && <p className="mb-2 font-mono text-sm">expected: “{ch.phrase}”</p>}
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
      ) : (
        <Card>
          <ol className="flex flex-col gap-2 font-mono text-xs">
            {events.map((e) => (
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

function SignalView({ kind, s }: { kind: string; s: Signals }) {
  const latency = s.reply_latency_ms;
  const latencyScore =
    latency === null ? null : Math.max(0, Math.min(1, 1 - (latency - T.humanMs) / (T.machineMs - T.humanMs)));
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm">
        heard: <span className="font-mono">“{s.transcript || "…"}”</span>
      </p>
      {kind === "whisper_phrase" && <Meter label="Task Match" value={s.task_match} threshold={T.task} />}
      {kind === "whisper_phrase" && <Meter label="Whisper Score" value={s.whisper_score} threshold={T.whisper} />}
      {/* full credit only at or under human_ms, matching the Policy's "slow reply" Reason */}
      <Meter label="Reply Latency" value={latencyScore} threshold={1} suffix={latency === null ? "none" : `${latency} ms`} />
      <Meter label="Spoof Score" value={s.spoof_score} good={false} threshold={T.spoof} />
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
