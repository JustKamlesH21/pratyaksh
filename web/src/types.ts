// Mirrors the verifier's JSON (src/pratyaksh/verification/verifier.py `_view`, domain.Step).

export type CallState = "awaiting_request" | "challenging" | "awaiting_app_approval" | "closed";
export type Outcome =
  | "passed"
  | "passed_pending_review"
  | "approved_in_app"
  | "blocked"
  | "declined_in_app"
  | "handed_to_agent"
  | "ended"
  | "abandoned";
export type Verdict = "PASS" | "STEP_UP" | "BLOCK";
export type ChallengeKind = "whisper_phrase" | "possession_code";
export type RequestKind = "balance_enquiry" | "add_payee" | "sim_swap" | "high_value_transfer" | "account_service";

export interface Customer {
  id: string;
  name: string;
  phone_masked: string;
  language: string;
}

export interface Signals {
  transcript: string;
  task_match: number | null;
  whisper_score: number | null;
  reply_latency_ms: number | null;
  spoof_score: number | null;
  spoken_digits: string | null;
  code_match: boolean | null;
  /** Live Microphone: a Whisper Phrase's dynamic range in dB; above policy.yaml's max_range_db it was played in digitally. */
  dynamic_range_db?: number | null;
}

export interface AuditEvent {
  seq: number;
  kind: string;
  data: Record<string, unknown>;
  at: string;
}

export interface CallView {
  id: string;
  customer: { id: string; name: string };
  room: string;
  state: CallState;
  request: RequestKind | null;
  agent_review: boolean;
  review_status: "pending" | "approved" | "rejected" | null;
  challenges: { kind: ChallengeKind; prompt: string; phrase: string }[];
  evidence: { kind: ChallengeKind; signals: Signals }[];
  scores: number[];
  step_ups: number;
  verdict: Verdict | null;
  liveness: number | null;
  reasons: string[];
  outcome: Outcome | null;
  created_at: string;
  updated_at: string;
  events?: AuditEvent[];
  audit?: AuditCheck;
  transcript?: TranscriptLine[];
}

/** One line of a Call's Transcript (src/pratyaksh/verification/transcript.py). */
export interface TranscriptLine {
  seq: number;
  at: string;
  event: string;
  speaker: "agent" | "caller" | "system";
  text: string;
  tone?: "pass" | "stepup" | "block" | null;
  understood?: string | null;
  language?: "en" | "hi" | "kn";
  by_llm?: boolean;
  by_variant?: boolean;
  note?: string;
  challenge?: ChallengeKind;
  liveness?: number | null;
  signals?: Partial<Signals>;
  timings_ms?: Record<string, number>;
}

export interface CustomerRisk {
  customer: { id: string; name: string; phone_masked: string };
  risk: "high" | "elevated" | "normal";
  calls_7d: number;
  by_outcome_7d: Record<string, number>;
  blocked_24h: number;
  open_security_alerts: number;
  voice_pause: { active: boolean; minutes_left: number | null };
  last_blocked_call: string | null;
  recent: { id: string; request: RequestKind | null; outcome: Outcome | null; created_at: string }[];
}

/** The Audit Trail's hash chain, recomputed by the verifier. */
export interface AuditCheck {
  intact: boolean;
  events: number;
  broken_at: number | null;
  head: string | null;
}

export interface ReceiptClaims {
  call_id: string;
  sub: string;
  request: RequestKind | null;
  verdict: Verdict | null;
  outcome: Outcome | null;
  executable: boolean;
  audit_events: number;
  audit_head: string;
  iat: number;
  exp: number;
}

export interface Receipt {
  receipt: string;
  claims: ReceiptClaims;
}

export interface ReceiptCheck {
  valid: boolean;
  reason: string;
  claims: ReceiptClaims | null;
  redeemed?: boolean;
}

export interface Status {
  ready: boolean;
  database: { ok: boolean; dialect: string; audit_triggers: boolean };
  speech: { backend: string; whisper_model: string; warm: boolean };
  llm: { configured: boolean; model: string | null };
  warnings: string[];
}

export interface Stats {
  calls: number;
  by_outcome: Record<string, number>;
  blocked: number;
  avg_added_seconds: number | null;
  hearing_ms: { responses: number; p50: number | null; p95: number | null };
  attack_wave: { active: boolean; blocked: number; customers: number; minutes: number; threshold: number };
}

export interface DeviceMessage {
  id: number;
  call_id: string;
  kind: "possession_code" | "app_approval" | "security_alert";
  body: { code?: string; request?: RequestKind; request_text?: string; blocked_at?: string };
  created_at: string;
  expires_at: string;
  seconds_left: number;
}

export interface Inbox {
  customer: { id: string; name: string; phone_masked: string };
  messages: DeviceMessage[];
}

/** k of n, with a Wilson 95% confidence interval (null when n is 0). */
export interface EvalRate {
  k: number;
  n: number;
  rate: number | null;
  ci95: [number, number] | null;
}

export interface EvalSpread {
  n: number;
  median: number | null;
  p95: number | null;
  max: number | null;
  mean: number | null;
}

export interface EvalRun {
  id: number;
  created_at: string;
  label: string;
  summary: {
    calls: number;
    real_calls: number;
    clone_calls: number;
    catch_rate: number | null;
    false_reject_rate: number | null;
    avg_added_seconds_real: number | null;
    pass_threshold?: number;
    block_threshold?: number;
    // Eval Runs from Oct 28 on also carry counts, Wilson 95% intervals, breakdowns and latency.
    catch?: EvalRate;
    false_reject?: EvalRate;
    clone_pass?: EvalRate;
    by_condition?: Record<string, EvalRate>;
    by_channel?: Record<string, { false_reject: EvalRate; catch: EvalRate }>;
    by_language?: Record<string, { false_reject: EvalRate; catch: EvalRate }>;
    caught_by?: Record<string, number>;
    caught_by_only?: Record<string, number>;
    added_seconds?: { real: EvalSpread; clone: EvalSpread };
    hearing_ms?: EvalSpread;
    live_hearing_ms?: EvalSpread | null;
    speakers?: { eval: string[]; calibration: string[] | null; overlap: string[]; unlabelled_calls: number };
  };
  rows: {
    session_id: string;
    label: "real" | "clone";
    request: RequestKind;
    verdict: Verdict;
    liveness: number | null;
    added_seconds: number;
    reasons: string[];
    condition?: string | null;
    channel?: string;
    language?: string;
    caught_by?: string[];
    speaker?: string | null;
  }[];
  notes: string;
}

export const REQUEST_LABEL: Record<RequestKind, string> = {
  balance_enquiry: "Balance enquiry",
  add_payee: "Add payee",
  sim_swap: "SIM swap / password reset",
  high_value_transfer: "Transfer above ₹5 lakh",
  account_service: "Other account change",
};

/** One Customer on the Demo hub (GET /v1/demo/customers, behind CONSOLE_KEY: it carries the pairing token). */
export interface DemoCustomer extends Customer {
  device_token: string;
  voice_paused: boolean;
  pause_minutes_left: number | null;
  open_security_alerts: number;
  /** The laptop's LAN address (LAN_IP), for links a phone can open; null when not configured. */
  phone_host: string | null;
}
