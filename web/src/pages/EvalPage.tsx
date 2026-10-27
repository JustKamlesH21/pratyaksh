import { type CSSProperties, useEffect, useState } from "react";
import { ChartBar, Warning } from "@phosphor-icons/react";
import { api } from "../api";
import { Card, VerdictBadge } from "../components";
import type { EvalRate, EvalRun } from "../types";
import { REQUEST_LABEL } from "../types";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "-" : `${Math.round(v * 100)}%`);

/** "9/10 · 95% CI 60% to 98%", or "-" when nothing was measured. */
const counted = (r: EvalRate | undefined) =>
  !r || !r.n ? "-" : `${r.k}/${r.n}${r.ci95 ? ` · 95% CI ${pct(r.ci95[0])} to ${pct(r.ci95[1])}` : ""}`;

const FACTOR_LABEL: Record<string, string> = {
  possession_code: "Possession Code",
  whisper_score: "Whisper Score",
  task_match: "Task Match",
  spoof_score: "Spoof Score",
  reply_latency: "Reply Latency",
  no_reply: "No reply heard",
  other: "Other (low Liveness)",
};

const CONDITION_LABEL: Record<string, string> = {
  code_withheld: "Code withheld",
  code_supplied: "Code supplied (voice Signals alone)",
};

export default function EvalPage() {
  const [run, setRun] = useState<EvalRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.latestEval().then(setRun).catch((e) => setError(String(e)));
  }, []);

  if (error)
    return (
      <Card title="Eval Run">
        <p className="flex items-start gap-2 text-ink-soft">
          <ChartBar size={20} className="mt-0.5 shrink-0" />
          <span>No Eval Run yet. Record labelled calls, then run <code>pratyaksh-eval run data/eval/manifest.csv</code>.</span>
        </p>
      </Card>
    );
  if (!run)
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true" aria-label="Loading">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-28" />)}
      </div>
    );
  const s = run.summary;
  const added = s.added_seconds?.real;
  const hearing = s.live_hearing_ms ?? s.hearing_ms;
  const blocks = s.catch?.k ?? 0;
  const caught = Object.entries(s.caught_by ?? {});
  const groups = [
    ...Object.entries(s.by_channel ?? {}).map(([k, g]) => [`Channel: ${k}`, g] as const),
    ...Object.entries(s.by_language ?? {}).map(([k, g]) => [`Language: ${k}`, g] as const),
  ];
  const showGroups = Object.keys(s.by_channel ?? {}).length > 1 || Object.keys(s.by_language ?? {}).length > 1;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="font-display text-3xl font-semibold tracking-tight">Eval Run #{run.id}</h1>
        <span className="text-ink-soft">
          {run.label} · {new Date(run.created_at + "Z").toLocaleString()} · {s.real_calls} real, {s.clone_calls} Clone Calls
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat i={0} label="Catch Rate" value={pct(s.catch_rate)}
          note={s.catch ? `${counted(s.catch)} Clone Calls BLOCKed` : `share of ${s.clone_calls} Clone calls that ended in BLOCK`} />
        <Stat i={1} label="False Reject Rate" value={pct(s.false_reject_rate)}
          note={s.false_reject ? `${counted(s.false_reject)} real Calls not PASSed` : `share of ${s.real_calls} real calls not PASSed`} />
        <Stat i={2} label="Added Time (real)"
          value={added?.median != null ? `${added.median.toFixed(1)} s` : s.avg_added_seconds_real === null ? "-" : `${s.avg_added_seconds_real.toFixed(1)} s`}
          note={added?.median != null ? `median per real Call · p95 ${added.p95} s · max ${added.max} s` : "average per real call"} />
        {hearing && hearing.n ? (
          <Stat i={3} label="Hearing time" value={`${hearing.median} ms`}
            note={`median per Response${s.live_hearing_ms ? " (live Calls)" : " (Eval Run)"} · p95 ${hearing.p95} ms · max ${hearing.max} ms`} />
        ) : (
          <Stat i={3} label="Calls" value={String(s.calls)} note={`${s.real_calls} real, ${s.clone_calls} clone`} />
        )}
      </div>
      {s.clone_pass && s.clone_pass.n > 0 && (
        <p className="text-sm text-ink-soft">
          Clone Calls that PASSed: <span className="font-mono text-ink">{counted(s.clone_pass)}</span>. The rest of the
          Clone Calls not BLOCKed ended in STEP-UP (App Approval on the Registered Device).
        </p>
      )}
      {s.speakers && s.speakers.overlap.length > 0 && (
        <p role="alert" className="flex items-start gap-2 rounded-xl border border-block/40 bg-block/10 p-4 text-sm text-ink">
          <Warning size={20} weight="fill" className="mt-0.5 shrink-0 text-block" />
          <span>
            <strong>Speakers also used for calibration: {s.speakers.overlap.join(", ")}.</strong> The whisper threshold
            was tuned on their voices, so their Calls overstate these results.
          </span>
        </p>
      )}
      {run.notes && <p className="text-sm text-ink-soft">{run.notes}</p>}

      {(caught.length > 0 || Object.keys(s.by_condition ?? {}).length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {caught.length > 0 && (
            <Card title={`Caught by: Signals named in the Reasons of ${blocks} Clone BLOCKs`}>
              <ul className="flex flex-col gap-3">
                {caught.map(([factor, n]) => (
                  <li key={factor}>
                    <div className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="text-ink">{FACTOR_LABEL[factor] ?? factor}</span>
                      <span className="font-mono text-ink-soft">
                        {n}/{blocks}
                        {s.caught_by_only?.[factor] ? ` · only factor in ${s.caught_by_only[factor]}` : ""}
                      </span>
                    </div>
                    <div className="mt-1 h-2 rounded-full bg-sunken" aria-hidden="true">
                      <div className="h-2 rounded-full bg-block" style={{ width: `${blocks ? (100 * n) / blocks : 0}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-ink-soft">One Call can name several Signals, so the counts add up to more than the BLOCKs.</p>
            </Card>
          )}
          {Object.keys(s.by_condition ?? {}).length > 0 && (
            <Card title="Catch Rate by condition">
              <table className="w-full text-left text-sm">
                <tbody>
                  {Object.entries(s.by_condition ?? {}).map(([c, r]) => (
                    <tr key={c} className="border-t border-line first:border-t-0">
                      <td className="py-2 text-ink">{CONDITION_LABEL[c] ?? c}</td>
                      <td className="py-2 text-right font-mono text-lg font-semibold">{pct(r.rate)}</td>
                      <td className="py-2 pl-3 text-right font-mono text-xs text-ink-soft">{counted(r)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-3 text-xs text-ink-soft">
                With the code supplied, the attacker read the right Possession Code, so only the voice Signals can catch the Clone.
              </p>
            </Card>
          )}
        </div>
      )}

      {showGroups && (
        <Card title="By channel and language">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs font-semibold text-ink-soft">
                <tr><th className="py-2">Group</th><th>False Reject Rate</th><th>Catch Rate</th></tr>
              </thead>
              <tbody>
                {groups.map(([name, g]) => (
                  <tr key={name} className="border-t border-line">
                    <td className="py-2 text-ink">{name}</td>
                    <td className="font-mono text-xs">{g.false_reject.n ? `${pct(g.false_reject.rate)} · ${counted(g.false_reject)}` : "-"}</td>
                    <td className="font-mono text-xs">{g.catch.n ? `${pct(g.catch.rate)} · ${counted(g.catch)}` : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

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
                <th>Added Time</th>
                <th>Caught by / first Reason</th>
              </tr>
            </thead>
            <tbody>
              {run.rows.map((r) => {
                const wrong = (r.label === "clone" && r.verdict !== "BLOCK") || (r.label === "real" && r.verdict !== "PASS");
                const tags = [r.condition ? CONDITION_LABEL[r.condition]?.split(" (")[0] ?? r.condition : null,
                  r.channel === "cable" ? "cable" : null, r.language && r.language !== "unspecified" ? r.language : null].filter(Boolean);
                return (
                  <tr key={r.session_id} className={`border-t border-line ${wrong ? "bg-block/5" : ""}`}>
                    <td className="py-2 font-mono text-xs">{r.session_id}</td>
                    <td>
                      <span className={r.label === "clone" ? "font-semibold text-block" : "font-semibold text-pass"}>{r.label}</span>
                      {tags.length > 0 && <span className="block text-xs text-ink-soft">{tags.join(" · ")}</span>}
                    </td>
                    <td>{REQUEST_LABEL[r.request]}</td>
                    <td><VerdictBadge verdict={r.verdict} /></td>
                    <td className="font-mono">{r.liveness?.toFixed(2) ?? "-"}</td>
                    <td className="font-mono">{r.added_seconds.toFixed(1)} s</td>
                    <td className="max-w-md truncate text-ink-soft" title={r.reasons.join("\n")}>
                      {r.caught_by && r.caught_by.length > 0
                        ? r.caught_by.map((f) => FACTOR_LABEL[f] ?? f).join(", ")
                        : r.reasons[0]}
                    </td>
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
