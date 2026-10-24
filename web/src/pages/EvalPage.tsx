import { type CSSProperties, useEffect, useState } from "react";
import { api } from "../api";
import { Card, VerdictBadge } from "../components";
import type { EvalRun } from "../types";
import { REQUEST_LABEL } from "../types";

const pct = (v: number | null) => (v === null ? "-" : `${Math.round(v * 100)}%`);

export default function EvalPage() {
  const [run, setRun] = useState<EvalRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.latestEval().then(setRun).catch((e) => setError(String(e)));
  }, []);

  if (error)
    return (
      <Card title="Eval Run">
        <p className="text-ink-soft">No Eval Run yet. Record labelled calls, then run <code>pratyaksh-eval data/eval/manifest.csv</code>.</p>
      </Card>
    );
  if (!run)
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true" aria-label="Loading">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-28" />)}
      </div>
    );
  const s = run.summary;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-bold">Eval Run #{run.id}</h1>
        <span className="text-ink-soft">{run.label} · {new Date(run.created_at + "Z").toLocaleString()}</span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat i={0} label="Catch Rate" value={pct(s.catch_rate)} note={`share of ${s.clone_calls} Clone calls that ended in BLOCK`} />
        <Stat i={1} label="False Reject Rate" value={pct(s.false_reject_rate)} note={`share of ${s.real_calls} real calls not PASSed`} />
        <Stat i={2} label="Added Time (real)" value={s.avg_added_seconds_real === null ? "-" : `${s.avg_added_seconds_real.toFixed(1)} s`} note="average per real call" />
        <Stat i={3} label="Calls" value={String(s.calls)} note={`${s.real_calls} real, ${s.clone_calls} clone`} />
      </div>
      {run.notes && <p className="text-sm text-ink-soft">{run.notes}</p>}
      <Card title="Per call">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs font-semibold text-ink-soft">
              <tr>
                <th className="py-2">Session</th>
                <th>Label</th>
                <th>Request</th>
                <th>Verdict</th>
                <th>Liveness</th>
                <th>First reason</th>
              </tr>
            </thead>
            <tbody>
              {run.rows.map((r) => {
                const wrong = (r.label === "clone" && r.verdict !== "BLOCK") || (r.label === "real" && r.verdict !== "PASS");
                return (
                  <tr key={r.session_id} className={`border-t border-line ${wrong ? "bg-block/5" : ""}`}>
                    <td className="py-2 font-mono text-xs">{r.session_id}</td>
                    <td className={r.label === "clone" ? "font-semibold text-block" : "font-semibold text-pass"}>{r.label}</td>
                    <td>{REQUEST_LABEL[r.request]}</td>
                    <td><VerdictBadge verdict={r.verdict} /></td>
                    <td className="font-mono">{r.liveness?.toFixed(2) ?? "-"}</td>
                    <td className="max-w-md truncate text-ink-soft" title={r.reasons.join("\n")}>{r.reasons[0]}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Stat({ i, label, value, note }: { i: number; label: string; value: string; note: string }) {
  return (
    <div className="motion-enter rounded-xl border border-line bg-surface p-5" style={{ "--i": i } as CSSProperties}>
      <p className="text-sm font-medium text-ink-soft">{label}</p>
      <p className="mt-1 font-mono text-4xl font-semibold tracking-tight text-ink">{value}</p>
      <p className="mt-1 text-xs text-ink-soft">{note}</p>
    </div>
  );
}
