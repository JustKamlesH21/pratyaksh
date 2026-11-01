// Records the microphone with the browser's own MediaRecorder, then turns it into the 16 kHz mono WAV the verifier
// reads. MediaRecorder runs off the page's thread, so the Bank App's polling cannot drop audio from a statement.

const TARGET_RATE = 16000;
const DECODE_RATE = 48000; // Safari's decoder may refuse lower rates; downsample() does the rest
const TAIL_MS = 900; // the tap on Finished comes right on the last syllable: the number, the one part that must be heard

export interface Recording {
  stop: () => Promise<Blob>;
  cancel: () => void;
}

export async function startRecording(): Promise<Recording> {
  // The same capture as a Call: on iPhones, echo cancellation switches on voice processing that damages speech.
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
  });
  const mimeType = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"].find((t) => MediaRecorder.isTypeSupported(t));
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data);
  };
  recorder.start();

  const release = () => stream.getTracks().forEach((t) => t.stop());
  return {
    stop: async () => {
      await new Promise((resolve) => setTimeout(resolve, TAIL_MS));
      const stopped = new Promise((resolve) => {
        recorder.onstop = resolve;
      });
      recorder.stop();
      await stopped;
      release();
      return toWav(await decode(new Blob(chunks, { type: recorder.mimeType })));
    },
    cancel: () => {
      if (recorder.state !== "inactive") recorder.stop();
      release();
    },
  };
}

async function decode(blob: Blob): Promise<Float32Array> {
  const audio = await new OfflineAudioContext(1, 1, DECODE_RATE).decodeAudioData(await blob.arrayBuffer());
  const mono = new Float32Array(audio.length);
  for (let c = 0; c < audio.numberOfChannels; c++) {
    const channel = audio.getChannelData(c);
    for (let i = 0; i < mono.length; i++) mono[i] += channel[i] / audio.numberOfChannels;
  }
  return downsample(mono, audio.sampleRate);
}

/** Averages each stretch of input samples into one output sample, which also keeps out most aliasing. */
function downsample(samples: Float32Array, rate: number): Float32Array {
  if (rate <= TARGET_RATE) return samples;
  const out = new Float32Array(Math.floor((samples.length * TARGET_RATE) / rate));
  const step = rate / TARGET_RATE;
  for (let i = 0; i < out.length; i++) {
    const from = Math.floor(i * step);
    const to = Math.min(samples.length, Math.max(from + 1, Math.floor((i + 1) * step)));
    let sum = 0;
    for (let j = from; j < to; j++) sum += samples[j];
    out[i] = sum / (to - from);
  }
  return out;
}

function toWav(samples: Float32Array): Blob {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const text = (at: number, s: string) => [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, TARGET_RATE, true);
  view.setUint32(28, TARGET_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Blob([view], { type: "audio/wav" });
}
