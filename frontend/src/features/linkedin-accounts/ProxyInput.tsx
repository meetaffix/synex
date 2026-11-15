import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { requestFailureMessage } from "./copy";
import {
  PROXY_PROTOCOLS,
  buildProxyUrl,
  emptyProxy,
  isBlank,
  parseProxyUrl,
  proxyProblem,
  type ProxyParts,
  type ProxyProtocol,
} from "./proxy";
import type { ProxyTestResult } from "./schemas";
import { senderAccountsService } from "./service";

interface Props {
  /** The full proxy URL, or "" when there is none. */
  value: string;
  onChange: (url: string) => void;
  /** An address is already saved for this account; it is never shown. */
  configured?: boolean;
  /** Called when "Connect without a proxy" is used. */
  onClear?: () => void;
}

const selectClass =
  "flex h-9 w-full rounded-sm border border-input bg-background px-3 text-sm  focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30";

type TestState = { kind: "idle" } | { kind: "testing" } | { kind: "done"; result: ProxyTestResult } | { kind: "error"; message: string };

/** Paste a proxy URL to split it into editable fields, test it, or connect without one. */
export function ProxyInput({ value, onChange, configured = false, onClear }: Props) {
  const id = useId();
  const [parts, setParts] = useState<ProxyParts>(() => parseProxyUrl(value) ?? emptyProxy);
  const [paste, setPaste] = useState("");
  const [pasteError, setPasteError] = useState<string>();
  const [test, setTest] = useState<TestState>({ kind: "idle" });
  const [cleared, setCleared] = useState(false);

  const update = (next: ProxyParts) => {
    setParts(next);
    setTest({ kind: "idle" });
    setCleared(false);
    onChange(buildProxyUrl(next));
  };
  const set = <K extends keyof ProxyParts>(key: K, fieldValue: ProxyParts[K]) => update({ ...parts, [key]: fieldValue });

  const onPaste = (text: string) => {
    setPaste(text);
    if (!text.trim()) return setPasteError(undefined);
    const parsed = parseProxyUrl(text);
    if (parsed) {
      setPaste("");
      setPasteError(undefined);
      update(parsed);
    } else if (/^\w+:\/\//.test(text.trim()) || text.includes("@")) {
      setPasteError("That is not a proxy address. Use http://, https:// or socks5:// followed by host:port.");
    } else {
      setPasteError(undefined);
    }
  };

  const clear = () => {
    setParts(emptyProxy);
    setPaste("");
    setPasteError(undefined);
    setTest({ kind: "idle" });
    setCleared(true);
    onChange("");
    onClear?.();
  };

  const runTest = async () => {
    setTest({ kind: "testing" });
    try {
      setTest({ kind: "done", result: await senderAccountsService.testProxy(buildProxyUrl(parts)) });
    } catch (error) {
      setTest({ kind: "error", message: requestFailureMessage(error) });
    }
  };

  const problem = isBlank(parts) ? undefined : proxyProblem(parts);
  const ready = !isBlank(parts) && !proxyProblem(parts);

  return (
    <div className="grid gap-4">
      <p className="text-xs text-muted-foreground">
        A proxy is optional and mainly useful for agencies running many accounts.
      </p>
      {configured && isBlank(parts) && (
        <p className="text-xs text-muted-foreground">
          {cleared
            ? "The proxy will be removed when you save."
            : "A proxy is set. Its address is not shown. Paste a new one to replace it."}
        </p>
      )}
      <div className="grid gap-2">
        <Label htmlFor={`${id}-paste`}>Paste a proxy URL</Label>
        <Input
          id={`${id}-paste`}
          value={paste}
          onChange={(event) => onPaste(event.target.value)}
          placeholder="http://user:password@host:8080"
          autoComplete="off"
          aria-describedby={pasteError ? `${id}-paste-error` : undefined}
          aria-invalid={!!pasteError}
        />
        {pasteError && (
          <p id={`${id}-paste-error`} role="alert" className="text-xs text-danger">
            {pasteError}
          </p>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-[8rem_minmax(0,1fr)_6rem]">
        <div className="grid gap-2">
          <Label htmlFor={`${id}-protocol`}>Protocol</Label>
          <select
            id={`${id}-protocol`}
            className={selectClass}
            value={parts.protocol}
            onChange={(event) => set("protocol", event.target.value as ProxyProtocol)}
          >
            {PROXY_PROTOCOLS.map((protocol) => (
              <option key={protocol} value={protocol}>
                {protocol}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-2">
          <Label htmlFor={`${id}-host`}>Host</Label>
          <Input id={`${id}-host`} value={parts.host} onChange={(event) => set("host", event.target.value)} autoComplete="off" />
        </div>
        <div className="grid gap-2">
          <Label htmlFor={`${id}-port`}>Port</Label>
          <Input
            id={`${id}-port`}
            inputMode="numeric"
            value={parts.port}
            onChange={(event) => set("port", event.target.value.replace(/\D/g, ""))}
            autoComplete="off"
            className="tabular-nums"
          />
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor={`${id}-username`}>Username (optional)</Label>
          <Input id={`${id}-username`} value={parts.username} onChange={(event) => set("username", event.target.value)} autoComplete="off" />
        </div>
        <div className="grid gap-2">
          <Label htmlFor={`${id}-password`}>Proxy password (optional)</Label>
          <Input
            id={`${id}-password`}
            type="password"
            value={parts.password}
            onChange={(event) => set("password", event.target.value)}
            autoComplete="off"
          />
        </div>
      </div>
      {problem && (
        <p role="alert" className="text-xs text-danger">
          {problem}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => void runTest()} disabled={!ready} loading={test.kind === "testing"}>
          Test connection
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={clear}>
          Connect without a proxy
        </Button>
      </div>
      <TestOutcome state={test} />
    </div>
  );
}

function TestOutcome({ state }: { state: TestState }) {
  const failed = state.kind === "error" || (state.kind === "done" && !state.result.ok);
  const message =
    state.kind === "testing"
      ? "Testing the proxy. This can take up to 10 seconds."
      : state.kind === "error"
      ? state.message
      : state.kind === "done"
        ? state.result.ok
          ? `Proxy works. Exit IP ${state.result.exitIp}${state.result.country ? ` (${state.result.country})` : ""}, ${state.result.latencyMs} ms.`
          : (state.result.error?.message ?? "The proxy test failed.")
        : "";
  return (
    <p role="status" aria-live="polite" className={cn("min-h-4 text-sm", failed ? "text-danger" : "text-foreground")}>
      {state.kind === "idle" ? "" : `${failed ? "Test failed. " : ""}${message}`}
    </p>
  );
}
