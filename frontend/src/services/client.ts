const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8010";

// Retire any bearer credential left over from the old frontend. New sessions are HttpOnly.
localStorage.removeItem("synex.token");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** In Clerk mode the app registers a function here that returns the current Clerk session token. */
let tokenGetter: (() => Promise<string | null>) | null = null;
export function setTokenGetter(getter: (() => Promise<string | null>) | null) {
  tokenGetter = getter;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/** Unified request entry point against the SYNEX FastAPI backend. */
export async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  asText = false
): Promise<T> {
  let res: Response;
  try {
    const token = tokenGetter ? await tokenGetter() : null;
    res = await fetch(`${API_URL}${path}`, {
      method,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(
      0,
      "Cannot reach the API. Is the backend running on " + API_URL + "?"
    );
  }

  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.map((e: { msg: string }) => e.msg).join("; ") : data.message ?? message;
    } catch {
      /* non-json error body */
    }
    if (res.status === 401) {
      // Token expired or invalid — drop it so the app returns to login.
      window.dispatchEvent(new Event("synex:unauthorized"));
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  if (asText) return (await res.text()) as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** A file from the API (audio for a preview), fetched with the same credentials as every other call so it works across sites. */
export async function fetchBlob(path: string): Promise<Blob> {
  const token = tokenGetter ? await tokenGetter() : null;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { credentials: "include", headers: token ? { Authorization: `Bearer ${token}` } : {} });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Is the backend running on " + API_URL + "?");
  }
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  getText: (path: string) => request<string>("GET", path, undefined, true),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

export const config = { API_URL };
