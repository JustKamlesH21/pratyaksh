import type { CallView, Customer, EvalRun, Inbox } from "./types";

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

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
    throw new Error(`${res.status}: ${detail}`);
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
  calls: (limit = 50) => http<CallView[]>(`/v1/calls?limit=${limit}`),
  call: (id: string) => http<CallView>(`/v1/calls/${id}`),
  review: (id: string, approve: boolean, consoleKey: string, reviewer = "bank-agent") =>
    http<CallView>(`/v1/calls/${id}/review`, {
      method: "POST",
      headers: { "X-Console-Key": consoleKey },
      body: JSON.stringify({ approve, reviewer }),
    }),
  token: (customerId: string) =>
    http<{ url: string; token: string; room: string }>("/v1/livekit/token", {
      method: "POST",
      body: JSON.stringify({ customer_id: customerId }),
    }),
  latestEval: () => http<EvalRun>("/v1/eval-runs/latest"),
};

export function eventsUrl(): string {
  return `${API_URL.replace(/^http/, "ws")}/v1/events`;
}
