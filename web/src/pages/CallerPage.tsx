import { AudioPresets, Room, RoomEvent, Track, type AudioCaptureOptions, type RemoteTrack } from "livekit-client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ChatText, CheckCircle, DeviceMobile, Headset, type Icon, Microphone, PhoneCall, PhoneDisconnect, Prohibit,
  ShieldCheck, SpeakerSimpleLow, Warning,
} from "@phosphor-icons/react";
import { api } from "../api";
import { ErrorNote, Logo, useCustomers } from "../components";
import type { Outcome } from "../types";

type Status = "idle" | "connecting" | "in-call" | "ended";

/** One line of the conversation: what the bank said (its caption) or what the Verifier heard the Caller say. */
interface Line {
  at: number;
  who: "bank" | "you";
  text: string;
}

/** The Challenge the Caller is answering now. Whisper Phrase words are in the script the Voice Agent speaks. */
interface OpenChallenge {
  kind: "whisper_phrase" | "possession_code";
  words: string;
}

/** Data messages the Voice Agent sends on the "pratyaksh" topic. */
type AgentMessage =
  | { type: "caption"; text: string } // what the bank is saying, sent as its audio starts
  | { type: "heard"; text: string } // what the Verifier heard the Caller say, before the reply is voiced
  | { type: "challenge"; kind: OpenChallenge["kind"] | null; words: string }
  | { type: "outcome"; outcome: Outcome };

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
  if (/Hands-Free|Bluetooth/i.test(label)) return "Bluetooth call mode: 8 to 16 kHz, whispers get lost";
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

// The Caller counts as talking above this level (a close whisper with auto gain off sits around -45 dBFS,
// a quiet room near -65). It only drives what the screen says; the Voice Agent finds speech on its own.
const TALK_DB = -52;
// After the Caller stops for this long, the screen says the bank is checking (the Voice Agent ends a reply
// at the first pause, a Possession Code after a longer one).
const CHECK_AFTER_MS = 1200;
const CODE_CHECK_AFTER_MS = 2200;

type Phase = "waiting" | "bank" | "listening" | "checking" | "your-turn";

const PHASE_TEXT: Record<Phase, string> = {
  waiting: "Connecting to your bank…",
  bank: "The bank is speaking",
  listening: "Listening…",
  checking: "Checking…",
  "your-turn": "Your turn",
};

/** Before the Voice Agent sent the open Challenge as data, the page read it from the caption. */
function challengeInCaption(text: string): OpenChallenge | null {
  const whisper = /whisper these words\.\s*(.+?)\.?\s*$/i.exec(text);
  if (whisper) return { kind: "whisper_phrase", words: whisper[1] };
  if (/six-digit code/i.test(text)) return { kind: "possession_code", words: "" };
  return null;
}

const clock = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

const PASSED: Outcome[] = ["passed", "passed_pending_review", "approved_in_app"];
const BLOCKED: Outcome[] = ["blocked", "declined_in_app"];

/** How the end screen reads an Outcome: badge, headline, one sentence, colour and icon. */
function ending(outcome: Outcome | null): { badge: string | null; title: string; text: string; tone: string; icon: Icon } {
  if (outcome && PASSED.includes(outcome))
    return {
      badge: "PASS",
      title: "You're verified",
      text:
        outcome === "passed_pending_review"
          ? "A bank officer will confirm this high-value request shortly."
          : outcome === "approved_in_app"
            ? "You approved this request in your bank app."
            : "Your request is done.",
      tone: "pass",
      icon: CheckCircle,
    };
  if (outcome && BLOCKED.includes(outcome))
    return {
      badge: "BLOCK",
      title: "Call blocked",
      text:
        outcome === "declined_in_app"
          ? "You declined this request in your bank app, so nothing was changed."
          : "We could not verify this call, so for your safety nothing was changed.",
      tone: "block",
      icon: Prohibit,
    };
  if (outcome === "handed_to_agent")
    return {
      badge: "Handed to an officer",
      title: "A bank officer will help you",
      text: "The officer will verify you again before changing anything.",
      tone: "stepup",
      icon: Headset,
    };
  return {
    badge: null,
    title: "Call ended",
    text: outcome === "ended" ? "Thank you for calling." : "Nothing was changed on your account.",
    tone: "ink-soft",
    icon: PhoneDisconnect,
  };
}

const TONE: Record<string, string> = {
  pass: "bg-pass/12 text-pass ring-pass/30",
  block: "bg-block/12 text-block ring-block/30",
  stepup: "bg-stepup/12 text-stepup ring-stepup/30",
  "ink-soft": "bg-sunken text-ink-soft ring-line",
};

/** Bars that move while someone speaks. `levels` (0..1 each) follow the microphone; without them they
 *  animate in CSS (still, under reduced motion). */
function VoiceBars({ active, levels, className = "" }: { active: boolean; levels?: number[]; className?: string }) {
  const bars = levels ?? [0, 0, 0, 0, 0];
  return (
    <span className={`voice-bars ${active && !levels ? "is-active" : ""} ${className}`} aria-hidden>
      {bars.map((v, i) => (
        <span key={i} style={levels ? { transform: `scaleY(${0.18 + 0.82 * v})` } : undefined} />
      ))}
    </span>
  );
}

export default function CallerPage() {
  const [params] = useSearchParams();
  const customers = useCustomers();
  const [customer, setCustomer] = useState(() => params.get("customer") ?? "");
  const [status, setStatus] = useState<Status>("idle");
  const [lines, setLines] = useState<Line[]>([]);
  const [challenge, setChallenge] = useState<OpenChallenge | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const [mic, setMic] = useState(() => stored(MIC_KEY) ?? "");
  const [capture, setCapture] = useState<Capture | null>(null);
  const [micTrack, setMicTrack] = useState<MediaStreamTrack | null>(null);
  const [micHeld, setMicHeld] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [endedAt, setEndedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [phase, setPhase] = useState<Phase>("waiting");
  const level = useMicLevel(micTrack, micHeld);
  const roomRef = useRef<Room | null>(null);
  const stopHolding = useRef<(() => void) | null>(null);
  const audioHost = useRef<HTMLDivElement>(null);
  const transcriptBox = useRef<HTMLDivElement>(null);
  const structured = useRef(false); // the Voice Agent sends the open Challenge as data
  const turn = useRef({ spoke: false, lastTalk: 0, heard: false });
  const heardBank = useRef(false); // the bank has started speaking on this Call

  useEffect(
    () => () => {
      stopHolding.current?.();
      void roomRef.current?.disconnect();
    },
    [],
  );

  // A link from the demo hub (/call?customer=cust-rahul) chooses the Customer.
  useEffect(() => {
    const fromLink = params.get("customer");
    if (fromLink && status === "idle") setCustomer(fromLink);
  }, [params]);

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

  // The call timer.
  useEffect(() => {
    if (status !== "in-call") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [status]);

  // Whose turn it is, from who is making sound: the bank's voice, the Caller's microphone, or neither.
  const bankSpeaking = agentSpeaking || micHeld;
  useEffect(() => {
    if (status !== "in-call") return;
    const t = turn.current;
    const at = performance.now();
    if (bankSpeaking) {
      heardBank.current = true;
      turn.current = { spoke: false, lastTalk: 0, heard: false };
      setPhase("bank");
      return;
    }
    if (level.db > TALK_DB) {
      t.spoke = true;
      t.lastTalk = at;
      setPhase("listening");
      return;
    }
    if (!heardBank.current) {
      setPhase("waiting"); // the greeting has not started yet
      return;
    }
    const pause = challenge?.kind === "possession_code" ? CODE_CHECK_AFTER_MS : CHECK_AFTER_MS;
    setPhase(t.heard || (t.spoke && at - t.lastTalk > pause) ? "checking" : t.spoke ? "listening" : "your-turn");
  }, [level, bankSpeaking, status, challenge]);

  // Keep the newest line in view inside the conversation box (not the page: the status and the Challenge stay put).
  useEffect(() => {
    const box = transcriptBox.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [lines.length, status]);

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

  function onMessage(msg: AgentMessage) {
    const add = (who: Line["who"], text: string) => setLines((l) => [...l, { at: Date.now(), who, text }]);
    if (msg.type === "caption") {
      heardBank.current = true;
      add("bank", msg.text);
      if (!structured.current) {
        const open = challengeInCaption(msg.text);
        if (open) setChallenge(open);
      }
    } else if (msg.type === "heard") {
      add("you", msg.text);
      turn.current.heard = true;
    } else if (msg.type === "challenge") {
      structured.current = true;
      setChallenge(msg.kind ? { kind: msg.kind, words: msg.words } : null);
    } else if (msg.type === "outcome") {
      setOutcome(msg.outcome);
      setChallenge(null);
    }
  }

  function ended() {
    stopHolding.current?.();
    stopHolding.current = null;
    setMicTrack(null);
    setMicHeld(false);
    setAgentSpeaking(false);
    setEndedAt((at) => at ?? Date.now());
    setStatus("ended");
  }

  async function call() {
    if (MIC_BLOCKED) return;
    setError(null);
    setLines([]);
    setChallenge(null);
    setOutcome(null);
    setCapture(null);
    setStartedAt(null);
    setEndedAt(null);
    structured.current = false;
    heardBank.current = false;
    turn.current = { spoke: false, lastTalk: 0, heard: false };
    setPhase("waiting");
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
        try {
          onMessage(JSON.parse(new TextDecoder().decode(payload)) as AgentMessage);
        } catch (e) {
          console.warn("unreadable message from the Voice Agent", e);
        }
      });
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        setAgentSpeaking(speakers.some((p) => p.identity !== room.localParticipant.identity));
      });
      // The Voice Agent leaves when the Call is over; let its last words finish playing here first.
      room.on(RoomEvent.ParticipantDisconnected, () => {
        window.setTimeout(() => {
          if (roomRef.current === room) void hangUp();
        }, 1500);
      });
      room.on(RoomEvent.Disconnected, ended);

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true, options);
      setStartedAt(Date.now());
      setNow(Date.now());
      setStatus("in-call");
      await report(room);
      void listMics(); // names are readable once the microphone is allowed
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("idle");
    }
  }

  async function hangUp() {
    const room = roomRef.current;
    roomRef.current = null;
    await room?.disconnect();
    ended();
  }

  const unnamed = mics.length > 0 && mics.every((d) => !d.label);
  const name = customers.find((c) => c.id === customer)?.name;
  const chosen = mics.find((d) => d.deviceId === mic);
  const problem = chosen ? micProblem(chosen.label) : null;

  const micPicker = (
    <div className="flex flex-col gap-1.5 text-sm">
      <label htmlFor="mic" className="font-medium text-ink-soft">Microphone</label>
      <select
        id="mic"
        className="min-h-12 rounded-xl border border-line bg-surface px-3 text-base text-ink disabled:opacity-40"
        value={mic}
        disabled={!!MIC_BLOCKED || status === "connecting"}
        onChange={(e) => void chooseMic(e.target.value)}
      >
        <option value="">System default</option>
        {mics.map((d, i) => (
          <option key={d.deviceId} value={d.deviceId}>
            {d.label || `Microphone ${i + 1}`}
            {micProblem(d.label) ? " (not recommended)" : ""}
          </option>
        ))}
      </select>
      {problem && (
        <p className="flex items-start gap-1.5 text-xs font-semibold text-block">
          <Warning size={14} className="mt-0.5 shrink-0" aria-hidden /> This microphone {problem}.
        </p>
      )}
      {unnamed && (
        <button className="self-start text-xs font-semibold text-accent underline" onClick={() => void listMics(true)}>
          Show microphone names
        </button>
      )}
    </div>
  );

  const captureNote = capture && (
    <p className="flex items-start gap-1.5 text-xs text-ink-soft" title="What the browser applied to the microphone">
      <Microphone size={14} className="mt-0.5 shrink-0" aria-hidden />
      <span>
        {capture.device} · noise suppression {onOff(capture.noiseSuppression)} · auto gain{" "}
        {onOff(capture.autoGainControl)} · echo cancellation {onOff(capture.echoCancellation)}
        {capture.sampleRate ? ` · ${capture.sampleRate / 1000} kHz` : ""}
      </span>
    </p>
  );

  const audio = <div ref={audioHost} className="hidden" />;

  // ---------------------------------------------------------------- before a Call
  if (status === "idle" || status === "connecting") {
    return (
      <div className="mx-auto flex w-full max-w-md flex-col gap-6">
        <div className="flex flex-col items-center gap-3 pt-2 text-center">
          <Logo size={56} />
          <h1 className="font-display text-2xl font-semibold tracking-tight">Call your bank</h1>
          <p className="max-w-xs text-sm text-ink-soft">
            The bank checks that it is really you, live, holding your registered phone. No voice is stored.
          </p>
        </div>
        <div className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-ink-soft">Calling as</span>
            <select
              className="min-h-12 rounded-xl border border-line bg-surface px-3 text-base text-ink"
              value={customer}
              disabled={status === "connecting"}
              onChange={(e) => setCustomer(e.target.value)}
            >
              <option value="">Choose a Customer…</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.phone_masked})
                </option>
              ))}
            </select>
          </label>
          {micPicker}
        </div>
        <button
          className="press inline-flex min-h-16 items-center justify-center gap-2.5 rounded-full bg-pass px-6 text-lg font-bold text-on-color disabled:cursor-not-allowed disabled:opacity-40"
          disabled={!customer || !!MIC_BLOCKED || status === "connecting"}
          onClick={call}
        >
          <PhoneCall size={24} weight="fill" aria-hidden /> {status === "connecting" ? "Connecting…" : "Call"}
        </button>
        <ErrorNote error={MIC_BLOCKED ?? error} />
        <details className="text-xs text-ink-soft">
          <summary className="cursor-pointer font-semibold">Red-team mode</summary>
          <p className="mt-2">
            On the attacker laptop, choose the victim as "Calling as", pick{" "}
            <b>CABLE Output (VB-Audio Virtual Cable)</b> as the Microphone. <code>attacker/clone_speak.py</code> plays the
            Clone into that cable, so the Voice Agent hears the Clone, not you.
          </p>
        </details>
        {audio}
      </div>
    );
  }

  const transcript = (
    <section aria-label="Conversation" className="flex flex-col gap-2">
      {lines.length === 0 ? (
        <p className="flex items-center gap-2 py-3 text-sm text-ink-soft">
          <ChatText size={18} aria-hidden /> What you and the bank say appears here.
        </p>
      ) : (
        <ol className="flex flex-col gap-2" aria-live="polite">
          {lines.map((l, i) => (
            <li
              key={l.at + "-" + i}
              className={`motion-enter max-w-[85%] rounded-2xl px-3.5 py-2.5 text-base leading-snug ${
                l.who === "bank"
                  ? "self-start rounded-bl-md bg-sunken text-ink"
                  : "self-end rounded-br-md bg-accent/15 text-ink ring-1 ring-accent/25"
              } ${i < lines.length - 2 ? "opacity-75" : ""}`}
            >
              <span className="mb-0.5 block text-[11px] font-semibold tracking-wide text-ink-soft uppercase">
                {l.who === "bank" ? "Bank" : "You"}
              </span>
              {l.text}
            </li>
          ))}
        </ol>
      )}
    </section>
  );

  // ---------------------------------------------------------------- after a Call
  if (status === "ended") {
    const end = ending(outcome);
    const Glyph = end.icon;
    return (
      <div className="mx-auto flex w-full max-w-md flex-col gap-6">
        <div className="flex flex-col items-center gap-3 pt-4 text-center" aria-live="polite">
          <span className={`motion-pop grid size-24 place-items-center rounded-full ring-1 ${TONE[end.tone]}`}>
            <Glyph size={52} weight="fill" aria-hidden />
          </span>
          {end.badge && (
            <span className={`motion-pop rounded-full px-3 py-1 text-sm font-bold ring-1 ${TONE[end.tone]}`}>{end.badge}</span>
          )}
          <h1 className="font-display text-3xl font-semibold tracking-tight">{end.title}</h1>
          <p className="max-w-xs text-ink-soft">{end.text}</p>
          {startedAt && (
            <p className="font-mono text-sm text-ink-soft">
              {name ? `${name} · ` : ""}call lasted {clock((endedAt ?? Date.now()) - startedAt)}
            </p>
          )}
        </div>
        <ErrorNote error={error} />
        {lines.length > 0 && (
          <div ref={transcriptBox} className="max-h-[45dvh] overflow-y-auto overscroll-contain rounded-2xl border border-line bg-surface p-3">
            {transcript}
          </div>
        )}
        <div className="flex flex-col gap-2">
          <button
            className="press inline-flex min-h-14 items-center justify-center gap-2 rounded-full bg-pass px-6 text-lg font-bold text-on-color disabled:opacity-40"
            disabled={!customer || !!MIC_BLOCKED}
            onClick={call}
          >
            <PhoneCall size={22} weight="fill" aria-hidden /> Call again
          </button>
          <button
            className="press min-h-12 rounded-full px-6 text-sm font-semibold text-ink-soft ring-1 ring-line hover:text-ink"
            onClick={() => setStatus("idle")}
          >
            Change Customer or microphone
          </button>
        </div>
        {audio}
      </div>
    );
  }

  // ---------------------------------------------------------------- during a Call
  const youTalking = phase === "listening";
  const meter = Math.max(0, Math.min(1, (level.db + 70) / 60));
  const bars = [0.55, 0.85, 1, 0.75, 0.5].map((k) => (youTalking ? Math.min(1, meter * k * 1.4) : 0));
  const end = outcome ? ending(outcome) : null;

  return (
    <div className="mx-auto flex h-[calc(100dvh-6.5rem)] min-h-[34rem] w-full max-w-md flex-col">
      {/* who is on the line, and for how long */}
      <header className="flex items-center gap-3 rounded-2xl border border-line bg-surface px-4 py-3">
        <Logo size={40} />
        <div className="min-w-0 flex-1">
          <p className="font-semibold leading-tight">Your bank</p>
          <p className="truncate text-sm text-ink-soft">{name ? `Calling as ${name}` : "Connected"}</p>
        </div>
        <div className="flex flex-col items-end">
          <span className="font-mono text-lg font-semibold tabular-nums">{startedAt ? clock(now - startedAt) : "0:00"}</span>
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-pass">
            <ShieldCheck size={12} weight="fill" aria-hidden /> Secure line
          </span>
        </div>
      </header>

      {/* whose turn it is */}
      <div className="flex flex-col items-center gap-3 py-5 text-center">
        <div className="relative grid size-28 place-items-center">
          <span
            className={`speaking-ring absolute inset-0 rounded-full ${
              phase === "bank" ? "is-active text-accent" : youTalking ? "is-active text-pass" : "text-line"
            }`}
            aria-hidden
          />
          <span
            className={`relative grid size-24 place-items-center rounded-full ring-1 ${
              phase === "bank"
                ? "bg-accent/15 text-accent ring-accent/40"
                : phase === "checking"
                  ? "bg-stepup/12 text-stepup ring-stepup/30"
                  : phase === "waiting"
                    ? "bg-sunken text-ink-soft ring-line"
                    : "bg-pass/12 text-pass ring-pass/30"
            }`}
          >
            {phase === "bank" ? (
              <VoiceBars active />
            ) : phase === "checking" || phase === "waiting" ? (
              <span className="typing inline-flex gap-1.5" aria-hidden>
                <span />
                <span />
                <span />
              </span>
            ) : (
              <VoiceBars active={youTalking} levels={bars} />
            )}
          </span>
        </div>
        <p
          className={`font-display text-3xl font-semibold tracking-tight ${
            phase === "bank"
              ? "text-accent"
              : phase === "checking"
                ? "text-stepup"
                : phase === "waiting"
                  ? "text-ink-soft"
                  : "text-pass"
          }`}
          aria-live="polite"
        >
          {PHASE_TEXT[phase]}
        </p>
      </div>

      {/* the open Challenge, or the Outcome as soon as the bank decides */}
      {end ? (
        <div className={`motion-pop flex items-center gap-3 rounded-2xl px-4 py-4 ring-1 ${TONE[end.tone]}`} aria-live="polite">
          <end.icon size={32} weight="fill" aria-hidden />
          <div>
            {end.badge && <p className="text-sm font-bold">{end.badge}</p>}
            <p className="font-semibold text-ink">{end.title}</p>
          </div>
        </div>
      ) : challenge?.kind === "whisper_phrase" ? (
        <div className="motion-pop flex flex-col gap-3 rounded-2xl border border-accent/40 bg-accent/10 p-4" aria-live="polite">
          <p className="text-sm font-semibold text-accent">Whisper these words</p>
          <p className="font-display text-[1.75rem] leading-snug font-semibold text-ink break-words">{challenge.words}</p>
          <p className="inline-flex items-center gap-2 self-start rounded-full bg-surface px-3 py-1.5 text-sm font-semibold text-ink ring-1 ring-line">
            <SpeakerSimpleLow size={16} weight="bold" aria-hidden /> Whisper, don't speak
          </p>
        </div>
      ) : challenge?.kind === "possession_code" ? (
        <div className="motion-pop flex items-center gap-4 rounded-2xl border border-accent/40 bg-accent/10 p-4" aria-live="polite">
          <span className="grid size-14 shrink-0 place-items-center rounded-xl bg-surface text-accent ring-1 ring-line">
            <DeviceMobile size={30} aria-hidden />
          </span>
          <div>
            <p className="text-lg font-semibold leading-snug text-ink">Read the 6-digit code from your bank app</p>
            <p className="text-sm text-ink-soft">Say the digits one by one, in your normal voice.</p>
          </div>
        </div>
      ) : null}

      {/* the conversation so far */}
      <div
        ref={transcriptBox}
        className="mt-4 min-h-28 flex-1 basis-0 overflow-y-auto overscroll-contain rounded-2xl border border-line bg-surface p-3"
      >
        {transcript}
      </div>

      <details className="mt-3 rounded-2xl border border-line bg-surface p-3 text-sm">
        <summary className="cursor-pointer font-semibold text-ink-soft">Microphone settings</summary>
        <div className="mt-3 flex flex-col gap-3">
          {micPicker}
          {captureNote}
        </div>
      </details>
      <ErrorNote error={error} />

      {/* thumb zone: the microphone level and Hang up */}
      <div className="pt-4 pb-[env(safe-area-inset-bottom)]">
        {micTrack && (
          <div className="mb-4 flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Microphone size={16} className={micHeld ? "text-ink-soft" : level.silent ? "text-block" : "text-pass"} aria-hidden />
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-sunken" title={`${level.db.toFixed(0)} dBFS`}>
                <div
                  className={`h-full origin-left rounded-full motion-safe:transition-transform motion-safe:duration-100 ${
                    level.silent ? "bg-block" : "bg-pass"
                  }`}
                  style={{ transform: `scaleX(${micHeld ? 0 : meter})` }}
                />
              </div>
              <span className="w-20 text-right text-xs text-ink-soft">{micHeld ? "mic paused" : "your mic"}</span>
            </div>
            {level.silent && (
              <p className="text-xs font-semibold text-block" aria-live="polite">
                No sound from this microphone since the call began, so the bank cannot hear you. Open Microphone settings
                and pick Microphone Array (Realtek) or a wired headset.
              </p>
            )}
          </div>
        )}
        <div className="flex flex-col items-center gap-1.5">
          <button
            className="press grid size-18 place-items-center rounded-full bg-block text-on-color shadow-lg shadow-block/30"
            onClick={() => void hangUp()}
            aria-label="Hang up"
          >
            <PhoneDisconnect size={32} weight="fill" aria-hidden />
          </button>
          <span className="text-xs font-semibold text-ink-soft">Hang up</span>
        </div>
      </div>
      {audio}
    </div>
  );
}
