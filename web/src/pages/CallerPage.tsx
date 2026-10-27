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

/** Whispers are quiet broadband sound: noise suppression and auto gain treat them as noise, so both stay off.
 *  Echo cancellation is off too: on iPhones it switches on voice processing that strips whispers (whisper
 *  score 0.14-0.16 on Oct 27), and the microphone is held while the Voice Agent speaks, so there is no echo. */
function captureOptions(mic: string): AudioCaptureOptions {
  return {
    ...(mic ? { deviceId: { ideal: mic } } : {}),
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
  };
}

const AGENT_AUDIBLE = 3e-3; // -50 dBFS: the Voice Agent's voice is far louder, line noise far quieter
const HANGOVER_MS = 500; // the room still rings briefly after the last word

/** Half duplex: mute the Caller's microphone while the Voice Agent's voice is playing here, and briefly
 *  after. On a real iPhone Call (Oct 27) the agent heard its own words back ("How can I help you today?
 *  Add a PE") from the phone's speaker; the agent never listens while it speaks, but this phone plays
 *  its voice later than the agent sends it. Returns a function that stops it. */
function holdMicWhileAgentSpeaks(room: Room, agent: MediaStreamTrack, onHold: (held: boolean) => void): () => void {
  const ctx = new AudioContext();
  void ctx.resume();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(new MediaStream([agent])).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  let lastHeard = 0;
  let held = false;
  const timer = window.setInterval(() => {
    analyser.getFloatTimeDomainData(buf);
    let peak = 0;
    for (const v of buf) peak = Math.max(peak, Math.abs(v));
    const now = performance.now();
    if (peak > AGENT_AUDIBLE) lastHeard = now;
    const hold = now - lastHeard < HANGOVER_MS;
    if (hold === held) return;
    held = hold;
    const mic = room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track;
    void (hold ? mic?.mute() : mic?.unmute());
    onHold(hold);
  }, 30);
  return () => {
    window.clearInterval(timer);
    void ctx.close();
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

/** Microphones that measured badly on the demo laptop (Oct 27): why the Voice Agent would not hear the Caller. */
function micProblem(label: string): string | null {
  if (/AI Noise-cancelling/i.test(label)) return "sends silence to the browser (ASUS AI noise cancelling)";
  if (/Hands-Free|Bluetooth/i.test(label)) return "Bluetooth call mode: 8–16 kHz, whispers get lost";
  if (/CABLE Output/i.test(label)) return "the virtual cable: only for Red-team mode";
  return null;
}

// A working microphone may gate a quiet room to near zero (the Realtek array does), so only a microphone
// that has carried no sound at all for this long since the Call began counts as dead.
const SILENT_MS = 8000;
const SOUND = 1e-3; // -60 dBFS: speech near any working microphone peaks far above this

/** Live level of the microphone the Call is sending, and whether it has carried no sound since it started.
 *  Time while the microphone is held for the Voice Agent does not count. */
function useMicLevel(track: MediaStreamTrack | null, held: boolean) {
  const [level, setLevel] = useState({ db: -100, silent: false });
  const heldRef = useRef(held);
  heldRef.current = held;
  useEffect(() => {
    if (!track) return;
    const ctx = new AudioContext();
    void ctx.resume();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    ctx.createMediaStreamSource(new MediaStream([track])).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    let started = performance.now();
    let heardSound = false;
    const timer = window.setInterval(() => {
      if (heldRef.current) started = performance.now();
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      let peak = 0;
      for (const v of buf) {
        sum += v * v;
        peak = Math.max(peak, Math.abs(v));
      }
      heardSound ||= peak > SOUND;
      const db = 10 * Math.log10(sum / buf.length || 1e-10);
      setLevel({ db, silent: !heardSound && performance.now() - started > SILENT_MS });
    }, 100);
    return () => {
      window.clearInterval(timer);
      void ctx.close();
    };
  }, [track]);
  return level;
}

export default function CallerPage() {
  const [customer, setCustomer] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const [mic, setMic] = useState(() => stored(MIC_KEY) ?? "");
  const [capture, setCapture] = useState<Capture | null>(null);
  const [micTrack, setMicTrack] = useState<MediaStreamTrack | null>(null);
  const [micHeld, setMicHeld] = useState(false);
  const level = useMicLevel(micTrack, micHeld);
  const roomRef = useRef<Room | null>(null);
  const stopHolding = useRef<(() => void) | null>(null);
  const audioHost = useRef<HTMLDivElement>(null);

  useEffect(
    () => () => {
      stopHolding.current?.();
      void roomRef.current?.disconnect();
    },
    [],
  );

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
    setMicTrack(track);
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

  async function call() {
    if (MIC_BLOCKED) return;
    setError(null);
    setCaptions([]);
    setCapture(null);
    setStatus("connecting");
    try {
      const { url, token } = await api.token(customer);
      const options = captureOptions(mic);
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: options,
        // DTX off: Opus would otherwise stop sending frames it judges silent, and a whisper is nearly silent.
        publishDefaults: { audioPreset: AudioPresets.musicHighQuality, dtx: false, red: true },
      });
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind !== Track.Kind.Audio) return;
        audioHost.current?.appendChild(track.attach());
        stopHolding.current?.();
        stopHolding.current = holdMicWhileAgentSpeaks(room, track.mediaStreamTrack, setMicHeld);
      });
      room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
        if (topic !== "pratyaksh") return;
        const msg = JSON.parse(new TextDecoder().decode(payload));
        if (msg.type === "caption") setCaptions((c) => [...c, { at: Date.now(), text: msg.text }]);
      });
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        setAgentSpeaking(speakers.some((p) => p.identity !== room.localParticipant.identity));
      });
      room.on(RoomEvent.Disconnected, () => {
        stopHolding.current?.();
        stopHolding.current = null;
        setMicHeld(false);
        setStatus("ended");
      });

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
    stopHolding.current?.();
    stopHolding.current = null;
    await roomRef.current?.disconnect();
    roomRef.current = null;
    setMicTrack(null);
    setMicHeld(false);
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
                  {micProblem(d.label) ? " ⚠" : ""}
                </option>
              ))}
            </select>
            {(() => {
              const chosen = mics.find((d) => d.deviceId === mic);
              const problem = chosen ? micProblem(chosen.label) : null;
              return problem ? <p className="text-xs font-semibold text-block">⚠ This microphone {problem}.</p> : null;
            })()}
            {unnamed && (
              <button className="self-start text-xs font-semibold text-accent underline" onClick={() => void listMics(true)}>
                Show microphone names
              </button>
            )}
          </div>
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
              agentSpeaking || micHeld ? (
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
          {micTrack && status === "in-call" && (
            <div className="flex flex-col gap-1" aria-live="polite">
              <div className="h-2 overflow-hidden rounded-full bg-sunken" title={`${level.db.toFixed(0)} dBFS`}>
                <div
                  className={`h-full rounded-full ${level.silent ? "bg-block" : "bg-pass"}`}
                  style={{ width: `${Math.max(0, Math.min(100, ((level.db + 70) / 60) * 100))}%` }}
                />
              </div>
              {level.silent && (
                <p className="text-xs font-semibold text-block">
                  ⚠ No sound from this microphone since the call began, so the bank cannot hear you. Pick Microphone
                  Array (Realtek) or a wired headset above.
                </p>
              )}
            </div>
          )}
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
              <b>CABLE Output (VB-Audio Virtual Cable)</b> as the Microphone. <code>attacker/clone_speak.py</code> plays
              the Clone into that cable, so the Voice Agent hears the Clone, not you.
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
