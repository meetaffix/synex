import { useMutation, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, ApiError } from "@/services/client";

/** Voice notes: the audio is made or uploaded here, before launch, and stored on the server. Nothing is recorded or generated while a campaign sends. */

export const MAX_SECONDS = 60;
export const MAX_BYTES = 20 * 1024 * 1024;
export const MAX_SCRIPT = 1000;
export const LANGUAGES = [["en-US", "English (US)"], ["en-GB", "English (UK)"], ["en-IN", "English (India)"]] as const;

const audioSchema = z.object({ id: z.string(), kind: z.string(), language: z.string(), filename: z.string(), size: z.number(), durationSeconds: z.number().nullable(), durationChecked: z.boolean(), script: z.string().nullable().optional() });
export type VoiceAudio = z.infer<typeof audioSchema>;

const statusSchema = z.object({
  limits: z.object({ maxSeconds: z.number(), maxBytes: z.number(), maxScript: z.number(), formats: z.array(z.string()) }),
  languages: z.array(z.object({ id: z.string(), label: z.string() })),
  tts: z.object({ engine: z.string(), ready: z.boolean(), languages: z.record(z.string(), z.object({ label: z.string(), ready: z.boolean() })), missing: z.array(z.string()), note: z.string(), howTo: z.string() }),
});
const readinessSchema = z.array(z.object({ accountId: z.string(), name: z.string(), ready: z.boolean(), reasons: z.array(z.string()), roomToday: z.number() }));
const estimateSchema = z.object({ costUsd: z.number(), estimatedSeconds: z.number(), note: z.string() });

const read = <S extends z.ZodType>(schema: S, data: unknown): z.infer<S> => {
  const parsed = schema.safeParse(data);
  if (!parsed.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
  return parsed.data;
};

export const useVoiceStatus = () => useQuery({ queryKey: ["voice", "status"], queryFn: async () => read(statusSchema, await api.get("/voice-notes/status")), staleTime: 60_000 });
export const useVoiceReadiness = (campaignId: string, accountKey: string) =>
  useQuery({ queryKey: ["voice", "readiness", campaignId, accountKey], queryFn: async () => read(readinessSchema, await api.get(`/voice-notes/readiness?campaignId=${campaignId}`)) });
export const useScriptEstimate = (script: string, language: string) =>
  useQuery({ queryKey: ["voice", "estimate", script.length > 0], queryFn: async () => read(estimateSchema, await api.post("/voice-notes/estimate", { script, language })), enabled: script.trim().length > 0, staleTime: 30_000 });
export const useAudioMeta = (id: string | undefined) => useQuery({ queryKey: ["voice", "audio", id], queryFn: async () => read(audioSchema, await api.get(`/voice-notes/${id}`)), enabled: !!id, retry: false });

export const useUploadAudio = () =>
  useMutation({ mutationFn: async (v: { filename: string; data: string; language: string }) => read(audioSchema, await api.post("/voice-notes/upload", v)) });
export const useSynthesize = () =>
  useMutation({ mutationFn: async (v: { script: string; language: string }) => read(audioSchema, await api.post("/voice-notes/synthesize", v)) });

export const toBase64 = (bytes: ArrayBuffer): string => {
  let binary = "";
  const view = new Uint8Array(bytes);
  for (let i = 0; i < view.length; i += 0x8000) binary += String.fromCharCode(...view.subarray(i, i + 0x8000));
  return btoa(binary);
};

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

/** Record from the microphone for at most MAX_SECONDS and return a .wav file (the formats browsers record in are not ones LinkedIn accepts). */
export function startRecording(): Promise<{ stop: () => Promise<File> }> {
  return navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
    const recorder = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    const stopped = new Promise<void>((resolve) => { recorder.onstop = () => resolve(); });
    recorder.start();
    const limit = window.setTimeout(() => { if (recorder.state === "recording") recorder.stop(); }, MAX_SECONDS * 1000);
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
