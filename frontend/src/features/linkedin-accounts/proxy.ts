export type ProxyProtocol = "http" | "https" | "socks5";

export interface ProxyParts {
  protocol: ProxyProtocol;
  host: string;
  port: string;
  username: string;
  password: string;
}

export const PROXY_PROTOCOLS: ProxyProtocol[] = ["http", "https", "socks5"];

export const emptyProxy: ProxyParts = { protocol: "http", host: "", port: "", username: "", password: "" };

const isProtocol = (value: string): value is ProxyProtocol => (PROXY_PROTOCOLS as string[]).includes(value);

/** Splits a pasted proxy URL into its parts, or returns null when it is not a proxy URL. */
export function parseProxyUrl(text: string): ProxyParts | null {
  let url: URL;
  try {
    url = new URL(text.trim());
  } catch {
    return null;
  }
  const protocol = url.protocol.replace(":", "");
  if (!isProtocol(protocol) || !url.hostname) return null;
  return {
    protocol,
    host: url.hostname,
    port: url.port,
    username: decodeURIComponent(url.username),
    password: decodeURIComponent(url.password),
  };
}

export function proxyProblem(parts: ProxyParts): string | undefined {
  const port = Number(parts.port);
  if (!parts.host.trim()) return "Enter the proxy host.";
  if (!Number.isInteger(port) || port < 1 || port > 65535) return "Enter a port from 1 to 65535.";
  return undefined;
}

/** The full URL for the parts, or "" while they are incomplete or invalid. */
export function buildProxyUrl(parts: ProxyParts): string {
  if (proxyProblem(parts)) return "";
  const auth = parts.username
    ? `${encodeURIComponent(parts.username)}:${encodeURIComponent(parts.password)}@`
    : "";
  return `${parts.protocol}://${auth}${parts.host.trim()}:${parts.port}`;
}

export const isBlank = (parts: ProxyParts) =>
  !parts.host && !parts.port && !parts.username && !parts.password;
