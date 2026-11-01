import type {
  CallView, ConsentOverview, Customer, CustomerRisk, DemoCustomer, EvalRun, Inbox, MyVoice, Receipt, ReceiptCheck, Stats,
  Status, VoiceConsent,
} from "./types";

// HTTPS mode (start.ps1 with HTTPS=1) serves the API on this page's own origin through the dev server's proxy.
export const API_URL: string =
  import.meta.env.VITE_SAME_ORIGIN === "1"
    ? ""
    : ((import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000");

/** Thrown for non-2xx replies; `status` lets the Console ask for its key on a 403. */
export class HttpError extends Error {
  constructor(public status: number, public detail: string) {
    super(`${status}: ${detail}`);
  }
}

// The Console key (CONSOLE_KEY on the verifier). Kept for this browser tab only.
let consoleKeyValue = (() => {
  try {
    return sessionStorage.getItem("consoleKey") ?? "";
  } catch {
    return "";
  }
})();

export function consoleKey(): string {
  return consoleKeyValue;
}

export function setConsoleKey(key: string): void {
  consoleKeyValue = key;
  try {
    sessionStorage.setItem("consoleKey", key);
  } catch {
    /* private mode: keep it in memory */
  }
}

const staff = () => ({ "X-Console-Key": consoleKeyValue });

async function refused(res: Response): Promise<HttpError> {
  let detail = res.statusText;
  try {
    detail = (await res.json()).detail ?? detail;
  } catch {
    /* not JSON */
  }
  return new HttpError(res.status, detail);
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw await refused(res);
  return res.json() as Promise<T>;
}

export const api = {
  customers: () => http<Customer[]>("/v1/customers"),
  inbox: (customerId: string, deviceToken: string) =>
    http<Inbox>(`/v1/customers/${customerId}/inbox`, { headers: { "X-Device-Token": deviceToken } }),
  appApproval: (callId: string, customerId: string, deviceToken: string, approve: boolean) =>
    http(`/v1/calls/${callId}/app-approval`, {
      method: "POST",
      headers: { "X-Device-Token": deviceToken },
      body: JSON.stringify({ customer_id: customerId, approve }),
    }),
  finishNextSteps: (customerId: string, deviceToken: string) =>
    http<{ cleared: number }>(`/v1/customers/${customerId}/next-steps/done`, {
      method: "POST",
      headers: { "X-Device-Token": deviceToken },
    }),
  dismissAlerts: (customerId: string, deviceToken: string) =>
    http<{ dismissed: number }>(`/v1/customers/${customerId}/alerts/dismiss`, {
      method: "POST",
      headers: { "X-Device-Token": deviceToken },
    }),
  demoCustomers: () => http<DemoCustomer[]>("/v1/demo/customers", { headers: staff() }),
  demoReset: () => http<{ dismissed: number; ended: number }>("/v1/demo/reset", { method: "POST", headers: staff() }),
  calls: (limit = 50) => http<CallView[]>(`/v1/calls?limit=${limit}`, { headers: staff() }),
  call: (id: string) => http<CallView>(`/v1/calls/${id}`, { headers: staff() }),
  customerRisk: (customerId: string) => http<CustomerRisk>(`/v1/customers/${customerId}/risk`, { headers: staff() }),
  review: (id: string, approve: boolean, reviewer = "bank-agent") =>
    http<CallView>(`/v1/calls/${id}/review`, {
      method: "POST",
      headers: staff(),
      body: JSON.stringify({ approve, reviewer }),
    }),
  token: (customerId: string) =>
    http<{ url: string; token: string; room: string }>("/v1/livekit/token", {
      method: "POST",
      body: JSON.stringify({ customer_id: customerId }),
    }),
  latestEval: () => http<EvalRun>("/v1/eval-runs/latest"),
  status: () => http<Status>("/v1/status"),
  stats: () => http<Stats>("/v1/stats"),
  receipt: (callId: string) => http<Receipt>(`/v1/calls/${callId}/receipt`, { headers: staff() }),
  verifyReceipt: (receipt: string) =>
    http<ReceiptCheck>("/v1/receipts/verify", { method: "POST", body: JSON.stringify({ receipt }) }),
  redeemReceipt: (receipt: string) =>
    http<{ redeemed: boolean }>("/v1/receipts/redeem", {
      method: "POST",
      headers: staff(),
      body: JSON.stringify({ receipt }),
    }),
  myVoice: (customerId: string, deviceToken: string) =>
    http<MyVoice>(`/v1/customers/${customerId}/voice`, { headers: { "X-Device-Token": deviceToken } }),
  declineConsent: (id: string, customerId: string, deviceToken: string) =>
    http<VoiceConsent>(`/v1/voice-consents/${id}/decline`, {
      method: "POST",
      headers: { "X-Device-Token": deviceToken },
      body: JSON.stringify({ customer_id: customerId }),
    }),
  revokeConsent: (id: string, customerId: string, deviceToken: string) =>
    http<VoiceConsent>(`/v1/voice-consents/${id}/revoke`, {
      method: "POST",
      headers: { "X-Device-Token": deviceToken },
      body: JSON.stringify({ customer_id: customerId }),
    }),
  /** Not through http(): the browser must set the multipart Content-Type itself. */
  giveConsent: async (id: string, customerId: string, deviceToken: string, audio: Blob) => {
    const form = new FormData();
    form.append("customer_id", customerId);
    form.append("audio", audio, "statement.wav");
    const res = await fetch(`${API_URL}/v1/voice-consents/${id}/statement`, {
      method: "POST",
      headers: { "X-Device-Token": deviceToken },
      body: form,
    });
    if (!res.ok) throw await refused(res);
    return res.json() as Promise<{ granted: boolean; reason?: string; heard: string; match: number }>;
  },
  askConsent: (body: { customer_id: string; requester: string; purpose: string; minutes: number; max_uses: number }) =>
    http<VoiceConsent>("/v1/voice-consents", { method: "POST", headers: staff(), body: JSON.stringify(body) }),
  consentOverview: () => http<ConsentOverview>("/v1/voice-consents", { headers: staff() }),
  /** One Voice Use. The recording comes back only if it is allowed; a refusal is an HttpError 403 with the reason. */
  useVoice: async (body: { customer_id: string; requester: string; purpose: string; clip: string; consent_pass: string | null }) => {
    const res = await fetch(`${API_URL}/v1/voice-consents/use`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...staff() },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw await refused(res);
    return res.blob();
  },
};

/** Save the Transcript as a text file (with the Audit head). A fetch, not a link, so the key is sent. */
export async function downloadTranscript(callId: string): Promise<void> {
  const res = await fetch(`${API_URL}/v1/calls/${callId}/transcript?format=text`, { headers: staff() });
  if (!res.ok) throw new HttpError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), {
    href: url,
    download: `pratyaksh-call-${callId.slice(0, 8)}.txt`,
  });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** The Console's live feed. With CONSOLE_KEY set, the key goes in the first message (no WS headers). */
export function eventsUrl(): string {
  // An empty VITE_API_URL means the API is on this page's own origin (HTTPS mode proxies /v1).
  return `${(API_URL || window.location.origin).replace(/^http/, "ws")}/v1/events`;
}
