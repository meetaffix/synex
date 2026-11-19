/** Recording from the microphone as a 16 kHz mono .wav file, used by voice notes and by the local assistant. */

export const MAX_RECORD_SECONDS = 60;

/** Encode mono samples as a 16-bit PCM .wav file. */
export function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (at: number, value: string) => [...value].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); text(8, "WAVE"); text(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, "data"); view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return buffer;
}

export const toBase64 = (bytes: ArrayBuffer): string => {
  let binary = "";
  const view = new Uint8Array(bytes);
  for (let i = 0; i < view.length; i += 0x8000) binary += String.fromCharCode(...view.subarray(i, i + 0x8000));
  return btoa(binary);
};

/** Start recording; `stop()` ends it and returns a .wav file. Stops by itself at MAX_RECORD_SECONDS. */
export function startRecording(): Promise<{ stop: () => Promise<File> }> {
  return navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
    const recorder = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    const stopped = new Promise<void>((resolve) => { recorder.onstop = () => resolve(); });
    recorder.start();
    const limit = window.setTimeout(() => { if (recorder.state === "recording") recorder.stop(); }, MAX_RECORD_SECONDS * 1000);
    return {
      stop: async () => {
        window.clearTimeout(limit);
        if (recorder.state === "recording") recorder.stop();
        await stopped;
        stream.getTracks().forEach((t) => t.stop());
        const decoded = await new AudioContext().decodeAudioData(await new Blob(chunks).arrayBuffer());
        const rate = 16000;
        const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * rate)), rate);
        const source = offline.createBufferSource();
        source.buffer = decoded;
        source.connect(offline.destination);
        source.start();
        const rendered = await offline.startRendering();
        return new File([encodeWav(rendered.getChannelData(0), rate)], "recording.wav", { type: "audio/wav" });
      },
    };
  });
}
