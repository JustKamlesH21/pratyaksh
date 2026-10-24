import type { CallView, Customer, CustomerRisk, EvalRun, Inbox, Receipt, ReceiptCheck, Stats, Status } from "./types";

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

/** Thrown for non-2xx replies; `status` lets the Console ask for its key on a 403. */
export class HttpError extends Error {
  constructor(public status: number, detail: string) {
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

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new HttpError(res.status, detail);
  }
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
  dismissAlerts: (customerId: string, deviceToken: string) =>
    http<{ dismissed: number }>(`/v1/customers/${customerId}/alerts/dismiss`, {
      method: "POST",
      headers: { "X-Device-Token": deviceToken },
    }),
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
  return `${API_URL.replace(/^http/, "ws")}/v1/events`;
}
