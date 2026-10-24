import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { ErrorNote } from "../components";
import type { DeviceMessage, Inbox } from "../types";

/** The Customer's Registered Device. Open the pairing link on a phone:
 *  /bank?customer=cust-ananya&device=<token>  (printed by `pratyaksh-seed` and in the API log). */
export default function BankAppPage() {
  const [params] = useSearchParams();
  const customer = params.get("customer") ?? "";
  const device = params.get("device") ?? "";
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!customer || !device) return;
    let alive = true;
    const tick = () =>
      api
        .inbox(customer, device)
        .then((i) => alive && (setInbox(i), setError(null)))
        .catch((e) => alive && setError(String(e)));
    tick();
    const id = setInterval(tick, 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [customer, device]);

  async function answer(m: DeviceMessage, approve: boolean) {
    try {
      await api.appApproval(m.call_id, customer, device, approve);
      setInbox((i) => (i ? { ...i, messages: i.messages.filter((x) => x.id !== m.id) } : i));
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-4">
      {(!customer || !device) && (
        <div className="rounded-xl bg-white p-5 text-sm shadow-sm">
          <p className="font-bold">This phone is not paired.</p>
          <p className="mt-2 text-ink-soft">
            Open the pairing link for the Customer, printed by <code>pratyaksh-seed</code> and in the verifier log on the
            operator's laptop. Only the Customer's own phone should have it.
          </p>
        </div>
      )}
      {customer && device && (
        <div className="overflow-hidden rounded-[2.2rem] border-8 border-ink bg-white shadow-xl">
          <div className="bg-violet px-5 pb-5 pt-6 text-white">
            <p className="text-xs uppercase tracking-widest text-white/70">Your bank</p>
            <p className="text-lg font-bold">{inbox?.customer.name ?? "…"}</p>
            <p className="text-sm text-white/70">{inbox?.customer.phone_masked}</p>
          </div>
          <div className="flex min-h-80 flex-col gap-4 p-5">
            <ErrorNote error={error} />
            {inbox && inbox.messages.length === 0 && (
              <p className="mt-10 text-center text-ink-soft/70">No requests right now.</p>
            )}
            {inbox?.messages.map((m) =>
              m.kind === "possession_code" ? (
                <div key={m.id} className="rounded-2xl bg-paper p-4 text-center">
                  <p className="text-sm text-ink-soft">One-time code for your call with the bank</p>
                  <p className="my-2 font-mono text-4xl font-semibold tracking-[0.3em] text-ink">{m.body.code}</p>
                  <p className="text-xs text-ink-soft">Read it out on the call · expires in {m.seconds_left}s</p>
                </div>
              ) : (
                <div key={m.id} className="rounded-2xl border-2 border-amber bg-amber/10 p-4">
                  <p className="font-bold">Approve this request?</p>
                  <p className="mt-1 text-sm text-ink-soft">
                    Someone on a call with the bank asked to <b>{m.body.request_text}</b>.
                  </p>
                  <p className="mt-1 text-xs text-ink-soft">Expires in {m.seconds_left}s</p>
                  <div className="mt-4 grid grid-cols-2 gap-2">
                    <button className="rounded-xl bg-white py-3 font-bold text-block ring-1 ring-block/40" onClick={() => answer(m, false)}>
                      Decline
                    </button>
                    <button className="rounded-xl bg-pass py-3 font-bold text-white" onClick={() => answer(m, true)}>
                      Approve
                    </button>
                  </div>
                </div>
              ),
            )}
          </div>
        </div>
      )}
    </div>
  );
}
