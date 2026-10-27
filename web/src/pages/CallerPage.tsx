import { AudioPresets, Room, RoomEvent, Track, type AudioCaptureOptions, type RemoteTrack } from "livekit-client";
import { useEffect, useRef, useState } from "react";
import { ChatText, Microphone, PhoneCall, PhoneDisconnect, Waveform } from "@phosphor-icons/react";
import { api } from "../api";
import { Card, CustomerPicker, ErrorNote } from "../components";

type Status = "idle" | "connecting" | "in-call" | "ended";

interface Caption {
  at: number;
  text: string;
}

/** What the browser actually applied to the Caller's microphone. Sent to the Voice Agent as the "audio" attribute. */
interface Capture {
  device: string;
  noiseSuppression: boolean | null;
  autoGainControl: boolean | null;
  echoCancellation: boolean | null;
  sampleRate: number | null;
}

const MIC_KEY = "pratyaksh.mic";
const HEADSET_KEY = "pratyaksh.headset";

// Browsers expose the microphone only on HTTPS or localhost; over http://<LAN IP> this is undefined.
const MIC_BLOCKED =
  typeof navigator === "undefined" || !navigator.mediaDevices
    ? "This browser blocks the microphone on a plain http network address. On the laptop, open http://localhost:5173/call instead."
    : null;

function stored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function store(key: string, value: string | null) {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    // storage blocked: the choice lasts until reload
  }
}

/** Whispers are quiet broadband sound: noise suppression and auto gain treat them as noise, so both stay off. */
function captureOptions(mic: string, headset: boolean): AudioCaptureOptions {
  return {
    ...(mic ? { deviceId: { ideal: mic } } : {}),
    echoCancellation: !headset, // the Voice Agent plays through laptop speakers unless the Caller wears a headset
    noiseSuppression: false,
    autoGainControl: false,
  };
}

function captureOf(track: MediaStreamTrack): Capture {
  const s = track.getSettings();
  return {
    device: track.label || s.deviceId || "default",
    noiseSuppression: s.noiseSuppression ?? null,
    autoGainControl: s.autoGainControl ?? null,
    echoCancellation: s.echoCancellation ?? null,
    sampleRate: s.sampleRate ?? null,
  };
}

const onOff = (v: boolean | null) => (v === null ? "?" : v ? "on" : "off");

export default function CallerPage() {
  const [customer, setCustomer] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const [mic, setMic] = useState(() => stored(MIC_KEY) ?? "");
  const [headset, setHeadset] = useState(() => stored(HEADSET_KEY) === "1");
  const [capture, setCapture] = useState<Capture | null>(null);
  const roomRef = useRef<Room | null>(null);
  const audioHost = useRef<HTMLDivElement>(null);

  useEffect(() => () => void roomRef.current?.disconnect(), []);

  async function listMics(askPermission = false) {
    try {
      setMics((await Room.getLocalDevices("audioinput", askPermission)).filter((d) => d.deviceId !== "default"));
    } catch (e) {
      if (askPermission) setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    if (MIC_BLOCKED) return;
    void listMics();
    const onChange = () => void listMics();
    navigator.mediaDevices.addEventListener("devicechange", onChange);
    return () => navigator.mediaDevices.removeEventListener("devicechange", onChange);
  }, []);

  /** Show the applied capture settings and tell the Voice Agent about them. */
  async function report(room: Room) {
    const track = room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track?.mediaStreamTrack;
    if (!track) return;
    const c = captureOf(track);
    setCapture(c);
    try {
      await room.localParticipant.setAttributes({ audio: JSON.stringify(c) });
    } catch (e) {
      console.warn("could not send capture settings to the Voice Agent", e);
    }
  }

  async function chooseMic(id: string) {
    setMic(id);
    store(MIC_KEY, id || null);
    const room = roomRef.current;
    if (!room || status !== "in-call") return;
    try {
      await room.switchActiveDevice("audioinput", id || "default");
      await report(room);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function chooseHeadset(on: boolean) {
    setHeadset(on);
    store(HEADSET_KEY, on ? "1" : null);
  }

  async function call() {
    if (MIC_BLOCKED) return;
    setError(null);
    setCaptions([]);
    setCapture(null);
    setStatus("connecting");
    try {
      const { url, token } = await api.token(customer);
      const options = captureOptions(mic, headset);
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: options,
        // DTX off: Opus would otherwise stop sending frames it judges silent, and a whisper is nearly silent.
        publishDefaults: { audioPreset: AudioPresets.musicHighQuality, dtx: false, red: true },
      });
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
      await room.localParticipant.setMicrophoneEnabled(true, options);
      setStatus("in-call");
      await report(room);
      void listMics(); // names are readable once the microphone is allowed
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

  const inCall = status === "in-call" || status === "connecting";
  const unnamed = mics.length > 0 && mics.every((d) => !d.label);

  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
      <Card title="Call the bank">
        <div className="flex flex-col gap-4">
          <CustomerPicker value={customer} onChange={setCustomer} label="Calling as" />
          <div className="flex flex-col gap-1 text-sm">
            <label htmlFor="mic" className="font-medium text-ink-soft">Microphone</label>
            <select
              id="mic"
              className="rounded-lg border border-line bg-surface px-3 py-2 text-ink disabled:opacity-40"
              value={mic}
              disabled={!!MIC_BLOCKED || status === "connecting"}
              onChange={(e) => void chooseMic(e.target.value)}
            >
              <option value="">System default</option>
              {mics.map((d, i) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label || `Microphone ${i + 1}`}
                </option>
              ))}
            </select>
            {unnamed && (
              <button className="self-start text-xs font-semibold text-accent underline" onClick={() => void listMics(true)}>
                Show microphone names
              </button>
            )}
          </div>
          <label className="flex items-center gap-2 text-sm text-ink-soft">
            <input type="checkbox" checked={headset} disabled={inCall} onChange={(e) => chooseHeadset(e.target.checked)} />
            I'm using a headset <span className="text-xs">(echo cancellation off)</span>
          </label>
          {inCall ? (
            <button className="press inline-flex items-center justify-center gap-2 rounded-lg bg-block px-4 py-3 font-bold text-on-color" onClick={hangUp}>
              <PhoneDisconnect size={20} /> Hang up
            </button>
          ) : (
            <button
              className="press inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-3 font-bold text-on-color disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!customer || !!MIC_BLOCKED}
              onClick={call}
            >
              <PhoneCall size={20} /> {status === "ended" ? "Call again" : "Call"}
            </button>
          )}
          <p className="flex items-center gap-2 text-sm text-ink-soft" aria-live="polite">
            {status === "in-call" ? (
              agentSpeaking ? (
                <span className="inline-flex items-center gap-1.5 font-semibold text-accent">
                  <Waveform size={17} aria-hidden /> The bank is speaking
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
          {capture && (
            <p className="flex items-start gap-1.5 text-xs text-ink-soft" title="What the browser applied to the microphone">
              <Microphone size={14} className="mt-0.5 shrink-0" aria-hidden />
              <span>
                {capture.device} · noise suppression {onOff(capture.noiseSuppression)} · auto gain{" "}
                {onOff(capture.autoGainControl)} · echo cancellation {onOff(capture.echoCancellation)}
                {capture.sampleRate ? ` · ${capture.sampleRate / 1000} kHz` : ""}
              </span>
            </p>
          )}
          <ErrorNote error={MIC_BLOCKED ?? error} />
          <details className="text-xs text-ink-soft">
            <summary className="cursor-pointer font-semibold">Red-team mode</summary>
            <p className="mt-2">
              On the attacker laptop, choose the victim as "Calling as", pick{" "}
              <b>CABLE Output (VB-Audio Virtual Cable)</b> as the Microphone and tick "I'm using a headset" (no speaker
              echo reaches a cable). <code>attacker/clone_speak.py</code> plays the Clone into that cable, so the Voice
              Agent hears the Clone, not you.
            </p>
          </details>
        </div>
        <div ref={audioHost} className="hidden" />
      </Card>

      <Card title="What the bank said">
        {captions.length === 0 ? (
          <p className="flex items-center gap-2 text-ink-soft"><ChatText size={20} /> Captions appear here during the call.</p>
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
