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

export { encodeWav, startRecording, toBase64 } from "@/lib/recorder";
