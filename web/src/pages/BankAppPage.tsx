import { type CSSProperties, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bank, EyeSlash, Password, ShieldCheck, Siren } from "@phosphor-icons/react";
import { api } from "../api";
import { ErrorNote } from "../components";
import type { DeviceMessage, Inbox } from "../types";
import { REQUEST_LABEL } from "../types";

/** The Customer's Registered Device. Open the pairing link on a phone:
 *  /bank?customer=cust-ananya&device=<token>  (printed by `pratyaksh-seed`, in the API log and on /demo). */
export default function BankAppPage() {
  const [params] = useSearchParams();
  const customer = params.get("customer") ?? "";
  const device = params.get("device") ?? "";
  return (
    <div className="mx-auto flex max-w-sm flex-col gap-4">
      {(!customer || !device) && (
        <div className="rounded-xl border border-line bg-surface p-5 text-sm">
          <p className="font-bold">This phone is not paired.</p>
          <p className="mt-2 text-ink-soft">
            Open the pairing link for the Customer, printed by <code>pratyaksh-seed</code> and in the verifier log on the
            operator's laptop. Only the Customer's own phone should have it.
          </p>
        </div>
      )}
      {customer && device && <BankApp customer={customer} device={device} />}
    </div>
  );
}

/** The Bank App on one paired Registered Device: Possession Codes, App Approval prompts and Security
 *  Alerts, polled every second. `embedded` gives the phone a fixed height (the Demo hub shows three).
 *  `maskCodes` hides Possession Code digits (the projected hub mirror: an attacker in the room must not be
 *  able to read the code off the big screen; only the real phone shows it). */
export function BankApp({ customer, device, embedded = false, maskCodes = false, onAlertsDismissed }: {
  customer: string;
  device: string;
  embedded?: boolean;
  maskCodes?: boolean;
  onAlertsDismissed?: () => void;
}) {
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); // one tap at a time: a double tap must not answer twice

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

  async function once(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    try {
      await action();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const answer = (m: DeviceMessage, approve: boolean) =>
    once(async () => {
      await api.appApproval(m.call_id, customer, device, approve);
      setInbox((i) => (i ? { ...i, messages: i.messages.filter((x) => x.id !== m.id) } : i));
    });

  const dismissAlerts = () =>
    once(async () => {
      await api.dismissAlerts(customer, device);
      setInbox((i) => (i ? { ...i, messages: i.messages.filter((x) => x.kind !== "security_alert") } : i));
      onAlertsDismissed?.();
    });

  return (
    // A device frame stays dark in both themes, like a real phone.
    <div
      className={`overflow-hidden rounded-[2.2rem] border-[10px] border-bezel bg-surface ring-1 ring-line ${
        embedded ? "flex h-[26rem] flex-col" : ""
      }`}
    >
      <div className="bg-accent px-5 pb-5 pt-6 text-on-accent">
        <p className="flex items-center gap-1.5 text-xs font-medium opacity-80"><Bank size={15} /> Your bank</p>
        <p className="text-lg font-bold">{inbox?.customer.name ?? "…"}</p>
        <p className="text-sm opacity-80">{inbox?.customer.phone_masked}</p>
      </div>
      <div className={`flex flex-col gap-4 p-5 ${embedded ? "min-h-0 flex-1 overflow-y-auto" : "min-h-80"}`}>
        <ErrorNote error={error} />
        {!inbox && !error && (
          <div className="flex flex-col gap-3" aria-busy="true">
            <div className="skeleton h-24" />
            <div className="skeleton h-16" />
          </div>
        )}
        {inbox && inbox.messages.length === 0 && (
          <p className="mt-10 text-center text-ink-soft">No requests right now.</p>
        )}
        {inbox?.messages.map((m) =>
          m.kind === "security_alert" ? (
            <div key={m.id} className="alert-in rounded-xl border-2 border-block bg-surface p-4">
              <p className="flex items-center gap-2 font-bold text-block"><Siren size={20} weight="fill" aria-hidden /> Blocked call attempt</p>
              <p className="mt-1 text-sm text-ink">
                Someone called the bank as you
                {m.body.blocked_at && <> at {new Date(m.body.blocked_at + "Z").toLocaleTimeString()}</>}
                {m.body.request_text && <> and asked to <b>{m.body.request_text}</b></>}. We could not verify them, so
                nothing was changed.
              </p>
              <p className="mt-1 text-xs text-ink-soft">Voice requests on your account are paused until you dismiss this.</p>
              <p className="mt-1 text-xs text-ink-soft">If a caller says this check is "not working", hang up.</p>
              <button className="press mt-3 w-full rounded-lg bg-surface py-3 font-bold text-ink ring-1 ring-block/40 disabled:opacity-50" disabled={busy} onClick={dismissAlerts}>
                Dismiss
              </button>
            </div>
          ) : m.kind === "possession_code" ? (
            <PossessionCode key={m.id} message={m} masked={maskCodes} name={inbox?.customer.name ?? ""} />
          ) : (
            <div key={m.id} className="motion-enter rounded-xl border-2 border-accent bg-accent/10 p-4">
              <p className="flex items-center gap-2 font-bold"><ShieldCheck size={20} className="text-accent" /> Approve this request?</p>
              <p className="mt-1 text-sm text-ink">
                Someone on a call with the bank asked to <b>{m.body.request_text}</b>.
              </p>
              <TimeLeft message={m} />
              <p className="mt-2 text-xs text-ink-soft">Expires in {m.seconds_left}s</p>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <button className="press rounded-lg bg-surface py-3 font-bold text-block ring-1 ring-block/40 disabled:opacity-50" disabled={busy} onClick={() => answer(m, false)}>
                  Decline
                </button>
                <button className="press rounded-lg bg-accent py-3 font-bold text-on-accent disabled:opacity-50" disabled={busy} onClick={() => answer(m, true)}>
                  Approve
                </button>
              </div>
            </div>
          ),
        )}
      </div>
    </div>
  );
}

/** The Possession Code card: which Request it authorises, the digits grouped 3 + 3, and the anti-relay
 *  line (read it only if you are on the call; anyone who asks you for it is a scammer). Masked on the
 *  projector: the digits are not even in the page. */
function PossessionCode({ message: m, masked, name }: { message: DeviceMessage; masked: boolean; name: string }) {
  const code = m.body.code ?? "";
  const groups = [code.slice(0, 3), code.slice(3)].filter(Boolean);
  const request = m.body.request ? REQUEST_LABEL[m.body.request] : null;
  return (
    <div className="motion-enter rounded-xl bg-sunken p-4 text-center">
      <p className="flex items-center justify-center gap-1.5 text-sm text-ink-soft">
        <Password size={17} aria-hidden /> Code for your call with the bank
      </p>
      {request && <p className="mt-0.5 text-sm font-semibold text-ink">{request}</p>}
      {masked ? (
        <>
          <p className="my-2 font-mono text-[2.25rem] font-semibold tracking-[0.12em] text-ink-soft" aria-label="Possession Code hidden">
            ••• •••
          </p>
          <p className="flex items-center justify-center gap-1.5 text-xs font-medium text-ink-soft">
            <EyeSlash size={14} aria-hidden /> Shown only on {name.split(" ")[0] || "the Customer"}'s phone
          </p>
        </>
      ) : (
        <>
          <p className="my-2 font-mono text-[2.25rem] font-semibold tracking-[0.12em] text-ink" aria-label={code.split("").join(" ")}>
            {groups.map((g, k) => (
              <span key={k} className={k ? "ml-[0.45em]" : ""} aria-hidden>
                {g.split("").map((d, i) => (
                  <span key={i} className="motion-enter inline-block" style={{ "--i": k * 3 + i } as CSSProperties}>{d}</span>
                ))}
              </span>
            ))}
          </p>
          <p className="text-xs font-medium text-ink">
            Read it aloud only if <i>you</i> are on this call right now. If someone asks you for this code, it's a scam.
          </p>
        </>
      )}
      <TimeLeft message={m} />
      <p className="mt-2 font-mono text-xs text-ink-soft">Expires in {m.seconds_left}s</p>
    </div>
  );
}

/** Drains as the code or prompt runs out, so the Customer sees how long they have. */
function TimeLeft({ message }: { message: DeviceMessage }) {
  const total = (Date.parse(message.expires_at) - Date.parse(message.created_at)) / 1000;
  const share = total > 0 ? Math.max(0, Math.min(1, message.seconds_left / total)) : 0;
  return (
    <div className="mt-3 h-1 overflow-hidden rounded-full bg-line" role="presentation">
      <div
        className="h-full origin-left bg-accent motion-safe:transition-transform motion-safe:duration-1000 motion-safe:ease-linear"
        style={{ transform: `scaleX(${share})` }}
      />
    </div>
  );
}
