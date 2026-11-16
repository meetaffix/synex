import { useEffect, useRef, useState } from "react";
import { Mic, Square, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { fetchBlob } from "@/services/client";
import {
  LANGUAGES, MAX_BYTES, MAX_SCRIPT, MAX_SECONDS, startRecording, toBase64, useAudioMeta, useScriptEstimate, useSynthesize, useUploadAudio, useVoiceReadiness, useVoiceStatus,
} from "./voice";

interface Props {
  id: string;
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
  campaignId: string;
  accountIds: string[];
}

/** The settings of a voice note, always visible on the node: how it is made, its language, a preview, and whether each sender can send one. */
export function VoiceNoteFields({ id, config, onChange, campaignId, accountIds }: Props) {
  const mode = (config.mode as string) === "ai" ? "ai" : "direct";
  const language = (config.language as string) ?? "en-US";
  const script = String(config.script ?? "");
  const audioId = config.audioId as string | undefined;
  const status = useVoiceStatus();
  const meta = useAudioMeta(audioId);
  const upload = useUploadAudio();
  const synth = useSynthesize();
  const estimate = useScriptEstimate(script, language);
  const readiness = useVoiceReadiness(campaignId, accountIds.join(","));
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState<{ stop: () => Promise<File> } | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [url, setUrl] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const set = (change: Record<string, unknown>) => onChange({ ...config, ...change });

  useEffect(() => {
    if (!audioId) { setUrl(null); return; }
    let revoked = false;
    let made: string | null = null;
    fetchBlob(`/voice-notes/${audioId}/audio`).then((blob) => { if (!revoked) { made = URL.createObjectURL(blob); setUrl(made); } }).catch(() => setUrl(null));
    return () => { revoked = true; if (made) URL.revokeObjectURL(made); };
  }, [audioId]);

  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  const send = async (file: File) => {
    setError(null);
    if (file.size > MAX_BYTES) { setError("The file is larger than 20 MB."); return; }
    try {
      const made = await upload.mutateAsync({ filename: file.name, data: toBase64(await file.arrayBuffer()), language });
      set({ audioId: made.id });
    } catch (e) { setError(requestFailureMessage(e)); }
  };

  const toggleRecording = async () => {
    setError(null);
    if (recording) {
      const handle = recording;
      setRecording(null);
      try { await send(await handle.stop()); } catch { setError("The recording could not be saved. Try again, or upload a file instead."); }
      return;
    }
    try {
      setSeconds(0);
      setRecording(await startRecording());
    } catch {
      setError("The microphone could not be used. Allow microphone access for this site, or upload a file instead.");
    }
  };

  const makeAudio = async () => {
    setError(null);
    try { set({ audioId: (await synth.mutateAsync({ script, language })).id }); } catch (e) { setError(requestFailureMessage(e)); }
  };

  const tts = status.data?.tts;
  const ttsReady = !!tts?.languages[language]?.ready && tts.ready;

  return (
    <div className="grid gap-4">
      <p className="text-xs text-muted-foreground">The same recording goes to everyone, and it is made here before launch. Nothing is recorded or generated while the campaign sends.</p>
      <fieldset className="grid gap-2">
        <legend className="text-sm font-medium">How is it made?</legend>
        <label className="flex items-center gap-2 text-sm"><input type="radio" name={`${id}-mode`} checked={mode === "direct"} onChange={() => set({ mode: "direct" })} /> Direct: record it or upload a file</label>
        <label className="flex items-center gap-2 text-sm"><input type="radio" name={`${id}-mode`} checked={mode === "ai"} onChange={() => set({ mode: "ai" })} /> AI assisted: write a script and let a voice read it</label>
      </fieldset>
      <div className="grid gap-1 sm:max-w-xs">
        <Label htmlFor={`${id}-lang`}>Language and accent</Label>
        <NativeSelect id={`${id}-lang`} value={language} onChange={(e) => set({ language: e.target.value, ...(mode === "ai" ? { audioId: undefined } : {}) })}>
          {LANGUAGES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </NativeSelect>
      </div>

      {mode === "direct" ? (
        <div className="grid gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => fileInput.current?.click()} loading={upload.isPending}><Upload aria-hidden /> Upload audio</Button>
            <input ref={fileInput} type="file" accept=".m4a,.mp3,.wav,audio/*" className="sr-only" aria-label="Voice note file" tabIndex={-1}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void send(f); e.target.value = ""; }} />
            <Button type="button" variant={recording ? "destructive" : "outline"} size="sm" onClick={() => void toggleRecording()}>
              {recording ? <><Square aria-hidden /> Stop recording ({seconds}s)</> : <><Mic aria-hidden /> Record</>}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">.m4a, .mp3 or .wav, up to {MAX_BYTES / 1024 / 1024} MB and {MAX_SECONDS} seconds. Recording stops by itself at {MAX_SECONDS} seconds.</p>
        </div>
      ) : (
        <div className="grid gap-2">
          <Label htmlFor={`${id}-script`}>Script</Label>
          <Textarea id={`${id}-script`} rows={4} maxLength={MAX_SCRIPT} value={script} placeholder="Hi, it is Sam. I saw your talk and wanted to say thank you."
            onChange={(e) => set({ script: e.target.value, audioId: undefined })} />
          <p className="text-xs text-muted-foreground">{script.length} of {MAX_SCRIPT} characters. No variables: the same recording goes to everyone.</p>
          {estimate.data && <p className="text-xs text-muted-foreground" data-testid="voice-estimate">{estimate.data.note} About {Math.round(estimate.data.estimatedSeconds)} seconds. Cost: $0.</p>}
          {tts && !ttsReady && (
            <p role="note" className="rounded-md bg-surface-muted p-2 text-xs">
              The voice engine is not set up for {LANGUAGES.find(([v]) => v === language)?.[1]}. {tts.missing.length ? `Missing: ${tts.missing.join(", ")}. ` : ""}{tts.howTo} You can also record or upload the voice note instead.
            </p>
          )}
          <div><Button type="button" size="sm" variant="outline" disabled={!script.trim() || !ttsReady} loading={synth.isPending} onClick={() => void makeAudio()}>Make the audio</Button></div>
        </div>
      )}

      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <div className="grid gap-1" aria-live="polite">
        <h4 className="text-sm font-medium">Preview voice note</h4>
        {audioId && meta.data ? (
          <>
            <p className="text-xs text-muted-foreground">{meta.data.filename}{meta.data.durationSeconds !== null ? `, ${Math.round(meta.data.durationSeconds)} seconds` : ", length not checked"}. Previewing costs nothing.</p>
            {url ? <audio controls src={url} aria-label="Voice note preview" className="w-full max-w-md" /> : <p className="text-xs text-muted-foreground">Loading the audio.</p>}
          </>
        ) : <p className="text-xs text-muted-foreground">No audio yet. {mode === "ai" ? "Write the script, then make the audio." : "Record or upload one."}</p>}
      </div>

      <section aria-label="Sender voice readiness" className="grid gap-1">
        <h4 className="text-sm font-medium">Can the senders send it?</h4>
        {readiness.isLoading && <p className="text-xs text-muted-foreground">Checking the senders.</p>}
        {readiness.data?.length === 0 && <p className="text-xs text-muted-foreground">Choose a sender in step 1 first.</p>}
        <ul className="grid gap-1 text-sm">
          {readiness.data?.map((r) => (
            <li key={r.accountId}><span className="font-medium">{r.name}</span>: {r.ready ? `ready, ${r.roomToday} left today` : r.reasons.join(" ")}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
