export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly body: unknown;

  constructor(status: number, detail: string, body?: unknown) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function getCookie(name: string): string | null {
  for (const part of document.cookie.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function detailFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

export async function ensureCsrfCookie(): Promise<string | null> {
  const existing = getCookie("csrftoken");
  if (existing) return existing;
  await fetch("/api/auth/csrf", { credentials: "same-origin" });
  return getCookie("csrftoken");
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

export async function apiFetch<T = unknown>(
  path: string,
  { method = "GET", body, signal }: RequestOptions = {},
): Promise<T> {
  const upper = method.toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE_METHODS.has(upper)) {
    const token = await ensureCsrfCookie();
    if (token) headers["X-CSRFToken"] = token;
  }

  const response = await fetch(path, {
    method: upper,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const data = await parseBody(response);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      detailFrom(data, response.statusText || `Request failed (${response.status})`),
      data,
    );
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => apiFetch<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: "POST", body }),
};
