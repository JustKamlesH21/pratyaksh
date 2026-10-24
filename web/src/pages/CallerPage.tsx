import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Card, CustomerPicker, ErrorNote } from "../components";

type Status = "idle" | "connecting" | "in-call" | "ended";

interface Caption {
  at: number;
  text: string;
}

export default function CallerPage() {
  const [customer, setCustomer] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const roomRef = useRef<Room | null>(null);
  const audioHost = useRef<HTMLDivElement>(null);

  useEffect(() => () => void roomRef.current?.disconnect(), []);

  async function call() {
    setError(null);
    setCaptions([]);
    setStatus("connecting");
    try {
      const { url, token } = await api.token(customer);
      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio) audioHost.current?.appendChild(track.attach());
      });
      room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
        if (topic !== "pratyaksh") return;
        const msg = JSON.parse(new TextDecoder().decode(payload));
        if (msg.type === "caption") setCaptions((c) => [...c, { at: Date.now(), text: msg.text }]);
      });
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        setAgentSpeaking(speakers.some((p) => p.identity !== room.localParticipant.identity));
      });
      room.on(RoomEvent.Disconnected, () => setStatus("ended"));

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
      setStatus("in-call");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("idle");
    }
  }

  async function hangUp() {
    await roomRef.current?.disconnect();
    roomRef.current = null;
    setStatus("ended");
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
      <Card title="Call the bank">
        <div className="flex flex-col gap-4">
          <CustomerPicker value={customer} onChange={setCustomer} label="Calling as" />
          {status === "in-call" || status === "connecting" ? (
            <button className="press rounded-lg bg-block px-4 py-3 font-bold text-on-color" onClick={hangUp}>
              Hang up
            </button>
          ) : (
            <button
              className="press rounded-lg bg-accent px-4 py-3 font-bold text-on-color disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!customer}
              onClick={call}
            >
              {status === "ended" ? "Call again" : "Call"}
            </button>
          )}
          <p className="flex items-center gap-2 text-sm text-ink-soft" aria-live="polite">
            {status === "in-call" ? (
              agentSpeaking ? (
                <span className="inline-flex items-center gap-1.5 font-semibold text-accent">
                  <span className="live-dot" aria-hidden /> The bank is speaking
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 font-semibold text-pass">
                  <span className="live-dot" aria-hidden /> Your turn
                </span>
              )
            ) : (
              <>Status: <b className="text-ink">{status === "connecting" ? "connecting…" : status}</b></>
            )}
          </p>
          <ErrorNote error={error} />
          <details className="text-xs text-ink-soft">
            <summary className="cursor-pointer font-semibold">Red-team mode</summary>
            <p className="mt-2">
              On the attacker laptop, choose the victim here and set this browser's microphone to the virtual cable
              that <code>attacker/clone_speak.py</code> plays into.
            </p>
          </details>
        </div>
        <div ref={audioHost} className="hidden" />
      </Card>

      <Card title="What the bank said">
        {captions.length === 0 ? (
          <p className="text-ink-soft">Captions appear here during the call.</p>
        ) : (
          <ol className="flex flex-col gap-3">
            {captions.map((c, i) => (
              <li
                key={c.at + i}
                className={`motion-enter rounded-lg px-4 py-3 text-lg ${
                  i === captions.length - 1 ? "bg-accent/10 text-ink ring-1 ring-accent/30" : "bg-sunken text-ink-soft"
                }`}
              >
                {c.text}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
