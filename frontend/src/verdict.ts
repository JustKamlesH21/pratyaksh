// How a Call's Verdict reads on screen: which Signal decided it, one plain sentence, and the Signal ticks.
// Everything here is derived from the verifier's own CallView (the Policy's Reasons and the measured
// Signals), so the screen only ever shows what actually fired. Used by the Demo hub's Verdict Ribbon and
// the Console's Call detail.
import type { CallView, ChallengeKind } from "./types";

/** Mirrors the defaults in policy.yaml, for threshold marks and tick labels only (the Policy decides). */
export const T = { task: 0.7, whisper: 0.6, humanMs: 2500, machineMs: 6000, spoof: 0.85, micMaxDb: 60 };

export type Factor =
  | "possession_code"
  | "whisper_score"
  | "live_microphone"
  | "task_match"
  | "no_reply"
  | "spoof_score"
  | "whisper_phrase"
  | "liveness"
  | "voice_pause"
  | "risk_tier"
  | "app_approval";

export const FACTOR_LABEL: Record<Factor, string> = {
  possession_code: "Possession Code",
  whisper_score: "Whisper Score",
  live_microphone: "Live Microphone",
  task_match: "Task Match",
  no_reply: "No reply heard",
  spoof_score: "Spoof Score",
  whisper_phrase: "Whisper Phrase",
  liveness: "Liveness Score",
  voice_pause: "Voice Pause",
  risk_tier: "Risk Tier",
  app_approval: "App Approval",
};

export const CHALLENGE_LABEL: Record<ChallengeKind, string> = {
  whisper_phrase: "Whisper Phrase",
  possession_code: "Possession Code",
};

/** A Voice Pause refusal: a risky Request from a Customer whose Call was just blocked, refused before
 *  any Challenge (policy.voice_paused). */
export function isVoicePauseRefusal(call: CallView): boolean {
  return call.verdict === "BLOCK" && call.challenges.length === 0 && /voice requests are paused/i.test(call.reasons[0] ?? "");
}

/** Whether the Policy rejected a Whisper Phrase as played in digitally (live_microphone enforced or advisory). */
export function noLiveMic(call: CallView): boolean {
  return call.reasons.some((r) => /no live microphone/i.test(r));
}

/** The Signal, or rule, that decided the Verdict, read from the Policy's first Reason. */
export function decidedBy(call: CallView): Factor | null {
  if (!call.verdict) return null;
  if (call.outcome === "approved_in_app" || call.outcome === "declined_in_app") return "app_approval";
  const r = call.reasons[0] ?? "";
  if (/voice requests are paused/i.test(r)) return "voice_pause";
  if (/code read out does not match|no code was read out/i.test(r)) return "possession_code";
  if (/not whispered/i.test(r)) return "whisper_score";
  if (/no live microphone/i.test(r)) return "live_microphone";
  if (/phrase did not match/i.test(r)) return "task_match";
  if (/no reply was heard/i.test(r)) return "no_reply";
  if (/looks synthetic/i.test(r)) return "spoof_score";
  if (/Whisper Phrase/i.test(r)) return "whisper_phrase";
  if (/No Challenges needed/i.test(r)) return "risk_tier";
  if (/^Liveness/i.test(r)) return "liveness";
  return null;
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** One plain sentence for the Verdict, made only of what actually happened. A BLOCK uses the Policy's own
 *  Reason; a PASS lists the Signals that were met. */
export function headline(call: CallView, first: string): string {
  if (!call.verdict) return "";
  if (isVoicePauseRefusal(call)) return `Call-back refused · Voice Pause on ${first}`;
  const by = decidedBy(call);
  if (by === "app_approval")
    return call.outcome === "approved_in_app"
      ? `${first} approved the Request on the Registered Device.`
      : `${first} declined the Request on the Registered Device.`;
  if (call.verdict === "PASS") {
    if (by === "risk_tier") return "No Challenges needed for this Request.";
    const whisper = call.evidence.filter((e) => e.kind === "whisper_phrase").at(-1)?.signals;
    const parts: string[] = [];
    if (whisper && (whisper.whisper_score ?? 0) >= T.whisper) parts.push("live whisper");
    if (whisper && (whisper.task_match ?? 0) >= T.task) parts.push("right phrase");
    if (call.evidence.some((e) => e.kind === "possession_code" && e.signals.code_match)) parts.push(`code from ${first}'s phone`);
    return parts.length ? `${cap(parts.join(", "))}.` : call.reasons[0] ?? "";
  }
  // BLOCK and STEP-UP: the Policy's first Reason, without its "Challenge 2 (Possession Code): " label.
  const reason = (call.reasons[0] ?? "").replace(/^Challenge \d+ \([^)]*\):\s*/, "");
  return cap(reason.replace("the Registered Device", `${first}'s Registered Device`));
}

/** One Signal as it landed, in the order the Call measures them. `ok` is null when there is no threshold. */
export interface Tick {
  key: string;
  label: string;
  value: string;
  need?: string;
  ok: boolean | null;
}

/** The Signal ticks of a Call, in order, and the latest Spoof Score (advisory, set apart). */
export function signalTicks(call: CallView): { ticks: Tick[]; spoof: number | null } {
  const ticks: Tick[] = [];
  let spoof: number | null = null;
  call.evidence.forEach((ev, i) => {
    const s = ev.signals;
    if (s.spoof_score != null) spoof = s.spoof_score;
    if (ev.kind === "whisper_phrase") {
      ticks.push({
        key: `${i}-task`, label: "Task Match", value: s.task_match == null ? "not measured" : s.task_match.toFixed(2),
        need: `needs ≥ ${T.task.toFixed(2)}`, ok: s.task_match == null ? null : s.task_match >= T.task,
      });
      ticks.push({
        key: `${i}-whisper`, label: "Whisper Score", value: s.whisper_score == null ? "not measured" : s.whisper_score.toFixed(2),
        need: `needs ≥ ${T.whisper.toFixed(2)}`, ok: s.whisper_score == null ? null : s.whisper_score >= T.whisper,
      });
      // Only what the Policy decided: the raw range is shown nowhere while live_microphone is off.
      if (noLiveMic(call) && s.dynamic_range_db != null && s.dynamic_range_db > T.micMaxDb)
        ticks.push({
          key: `${i}-mic`, label: "Live mic", value: `${s.dynamic_range_db.toFixed(0)} dB, no room noise`,
          need: `range ≤ ${T.micMaxDb} dB`, ok: false,
        });
      ticks.push({
        key: `${i}-latency`, label: "Reply Latency",
        value: s.reply_latency_ms == null ? "no reply" : `${(s.reply_latency_ms / 1000).toFixed(1)} s`,
        need: `within ${(T.humanMs / 1000).toFixed(1)} s`, ok: s.reply_latency_ms == null ? false : s.reply_latency_ms <= T.humanMs,
      });
    } else {
      ticks.push({
        key: `${i}-code`, label: "Code Match",
        value: s.code_match === true ? "matches" : s.code_match === false ? "wrong code" : "none read",
        ok: s.code_match === true,
      });
    }
  });
  return { ticks, spoof };
}

/** "0:42" from two verifier timestamps (UTC, no zone suffix). */
export function elapsed(from: string, to: string): string {
  const s = Math.max(0, Math.round((Date.parse(to + "Z") - Date.parse(from + "Z")) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
