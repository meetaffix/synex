/** Microphone capture (16 kHz mono linear16) and playback of the agent's speech (24 kHz linear16). */

const WORKLET = `
class Downsampler extends AudioWorkletProcessor {
  constructor() { super(); this.buffer = []; this.ratio = sampleRate / 16000; this.pos = 0; }
  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;
    for (let i = 0; i < input.length; i++) {
      this.pos += 1;
      if (this.pos >= this.ratio) { this.pos -= this.ratio; this.buffer.push(input[i]); }
    }
    if (this.buffer.length >= 640) {
      const out = new Int16Array(this.buffer.length);
      for (let i = 0; i < out.length; i++) { const s = Math.max(-1, Math.min(1, this.buffer[i])); out[i] = s < 0 ? s * 0x8000 : s * 0x7fff; }
      this.port.postMessage(out.buffer, [out.buffer]);
      this.buffer = [];
    }
    return true;
  }
}
registerProcessor("synex-downsampler", Downsampler);
`;

export function voiceSupport(): { ok: true } | { ok: false; reason: string } {
  if (typeof window === "undefined" || !window.isSecureContext) return { ok: false, reason: "Voice needs a secure (https) page." };
  if (!navigator.mediaDevices?.getUserMedia) return { ok: false, reason: "This browser cannot use a microphone." };
  if (typeof AudioContext === "undefined" || typeof AudioWorkletNode === "undefined") return { ok: false, reason: "This browser cannot process audio for voice." };
  return { ok: true };
}

export class MicCapture {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;

  get active() {
    return this.stream !== null;
  }

  /** Throws the browser's error (NotAllowedError when the person says no). */
  async start(onChunk: (pcm: ArrayBuffer) => void): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    try {
      this.context = new AudioContext();
      const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
      await this.context.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      const source = this.context.createMediaStreamSource(this.stream);
      this.node = new AudioWorkletNode(this.context, "synex-downsampler");
      this.node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => onChunk(event.data);
      source.connect(this.node);
    } catch (error) {
      this.stop();
      throw error;
    }
  }

  stop() {
    this.node?.port.close();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.context?.close().catch(() => undefined);
    this.node = null;
    this.stream = null;
    this.context = null;
  }
}

export class Player {
  private context: AudioContext | null = null;
  private next = 0;
  private sources = new Set<AudioBufferSourceNode>();
  muted = false;
  onSpeaking: (speaking: boolean) => void = () => undefined;

  push(pcm: ArrayBuffer) {
    if (this.muted || pcm.byteLength < 2) return;
    this.context ??= new AudioContext({ sampleRate: 24000 });
    void this.context.resume().catch(() => undefined);
    const samples = new Int16Array(pcm, 0, Math.floor(pcm.byteLength / 2));
    const buffer = this.context.createBuffer(1, samples.length, 24000);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) data[i] = samples[i] / 0x8000;
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);
    this.next = Math.max(this.next, this.context.currentTime + 0.02);
    source.start(this.next);
    this.next += buffer.duration;
    this.sources.add(source);
    this.onSpeaking(true);
    source.onended = () => {
      this.sources.delete(source);
      if (this.sources.size === 0) this.onSpeaking(false);
    };
  }

  /** Stop at once: the person started speaking, or muted the replies. */
  flush() {
    this.sources.forEach((source) => {
      source.onended = null;
      try {
        source.stop();
      } catch {
        /* already finished */
      }
    });
    this.sources.clear();
    this.next = 0;
    this.onSpeaking(false);
  }

  close() {
    this.flush();
    void this.context?.close().catch(() => undefined);
    this.context = null;
  }
}
