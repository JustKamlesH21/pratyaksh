import { useEffect, useMemo, useState } from "react";
import { api, eventsUrl } from "../api";
import { Card, ErrorNote, Meter, OutcomeLabel, VerdictBadge } from "../components";
import type { CallView, Signals } from "../types";
import { REQUEST_LABEL } from "../types";

// Mirrors the defaults in policy.yaml, for drawing threshold marks only.
const T = { task: 0.7, whisper: 0.6, humanMs: 1200, machineMs: 3000, spoof: 0.85 };

function useLiveCalls() {
  const [calls, setCalls] = useState<Record<string, CallView>>({});
  const [connected, setConnected] = useState(false);

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
  return { list, connected, setCalls };
}

export default function ConsolePage() {
  const { list, connected, setCalls } = useLiveCalls();
  const [selected, setSelected] = useState<string | null>(null);
  const call = list.find((c) => c.id === selected) ?? list[0];

  return (
    <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
      <Card title={<span>Calls <span className={connected ? "text-pass" : "text-block"}>{connected ? "● live" : "● offline"}</span></span>}>
        {list.length === 0 && <p className="text-sm text-ink-soft/70">No calls yet. Place one from the Caller tab.</p>}
        <ul className="flex flex-col gap-1">
          {list.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setSelected(c.id)}
                className={`w-full rounded-lg px-3 py-2 text-left ${call?.id === c.id ? "bg-ink text-white" : "hover:bg-paper"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{c.customer.name}</span>
                  <VerdictBadge verdict={c.verdict} />
                </div>
                <div className="flex items-center justify-between text-xs opacity-80">
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
  );
}

function CallDetail({ call, onUpdate }: { call: CallView; onUpdate: (c: CallView) => void }) {
  const [tab, setTab] = useState<"evidence" | "audit">("evidence");
  const [events, setEvents] = useState(call.events ?? []);
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
      return;
    }
    let current = true; // ignore a slow reply for a Call that is no longer selected
    api.call(call.id).then((c) => current && setEvents(c.events ?? [])).catch(() => undefined);
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
            <p className="text-xs uppercase tracking-wide text-ink-soft">Caller claims to be</p>
            <p className="text-xl font-bold">{call.customer.name}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-ink-soft">Request</p>
            <p className="font-semibold">{call.request ? REQUEST_LABEL[call.request] : "—"}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-ink-soft">Liveness</p>
            <p className="font-mono text-xl">{call.liveness?.toFixed(2) ?? "—"}</p>
          </div>
          <div className="ml-auto flex flex-col items-end gap-1">
            <VerdictBadge verdict={call.verdict} />
            <OutcomeLabel outcome={call.outcome} />
          </div>
        </div>
        {call.reasons.length > 0 && (
          <ul className="mt-4 list-disc space-y-1 pl-5 text-sm">
            {call.reasons.map((r, i) => (
              <li key={i} className={i === 0 ? "font-semibold" : ""}>{r}</li>
            ))}
          </ul>
        )}
        {call.review_status === "pending" && (
          <div className="mt-4 flex items-center gap-3 rounded-lg bg-amber/15 p-3">
            <span className="text-sm font-semibold">Agent Review needed for this high-value request.</span>
            <input
              type="password"
              placeholder="console key"
              className="ml-auto w-36 rounded-md border border-ink/20 px-2 py-1 text-sm"
              value={consoleKey}
              onChange={(e) => saveKey(e.target.value)}
            />
            <button className="rounded-md bg-white px-3 py-1.5 text-sm font-bold text-block ring-1 ring-block/40" onClick={() => review(false)}>
              Reject
            </button>
            <button className="rounded-md bg-pass px-3 py-1.5 text-sm font-bold text-white" onClick={() => review(true)}>
              Approve
            </button>
          </div>
        )}
        {call.review_status && call.review_status !== "pending" && (
          <p className="mt-3 text-sm">Agent Review: <b>{call.review_status}</b></p>
        )}
        <ErrorNote error={error} />
      </Card>

      <div className="flex gap-2">
        {(["evidence", "audit"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold ${tab === t ? "bg-violet text-white" : "bg-white text-ink-soft"}`}
          >
            {t === "evidence" ? "Challenges & Signals" : "Audit Trail"}
          </button>
        ))}
      </div>

      {tab === "evidence" ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {call.challenges.length === 0 && <p className="text-sm text-ink-soft/70">No Challenges yet.</p>}
          {call.challenges.map((ch, i) => {
            const ev = call.evidence[i];
            return (
              <Card
                key={i}
                title={
                  <span className="flex items-center justify-between">
                    <span>{i + 1}. {ch.kind === "whisper_phrase" ? "Whisper Phrase" : "Possession Code"}</span>
                    {call.scores[i] !== undefined && <span className="font-mono normal-case">liveness {call.scores[i].toFixed(2)}</span>}
                  </span>
                }
              >
                {ch.phrase && <p className="mb-2 font-mono text-sm">expected: “{ch.phrase}”</p>}
                {ev ? <SignalView kind={ch.kind} s={ev.signals} /> : <p className="text-sm text-violet">waiting for the Caller…</p>}
              </Card>
            );
          })}
        </div>
      ) : (
        <Card>
          <ol className="flex flex-col gap-2 font-mono text-xs">
            {events.map((e) => (
              <li key={e.seq} className="grid grid-cols-[2.5rem_6rem_10rem_1fr] gap-2 border-b border-ink/5 pb-2">
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
          code read out: <span className="font-mono">{s.spoken_digits ?? "—"}</span>{" "}
          {s.code_match === true && <b className="text-pass">matches the device</b>}
          {s.code_match === false && <b className="text-block">does not match</b>}
        </p>
      )}
    </div>
  );
}
