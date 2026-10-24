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
  };
  rows: {
    session_id: string;
    label: "real" | "clone";
    request: RequestKind;
    verdict: Verdict;
    liveness: number | null;
    added_seconds: number;
    reasons: string[];
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
