import { vi } from "vitest";

export interface MockResponse {
  status?: number;
  body?: unknown;
}

type Handler = MockResponse | ((init: RequestInit | undefined) => MockResponse);

/** Stubs global fetch with a "METHOD /path" -> response table. */
export function mockFetch(table: Record<string, Handler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    const key = `${method} ${String(input)}`;
    const handler = table[key];
    if (!handler) throw new Error(`Unmocked request: ${key}`);
    const { status = 200, body } = typeof handler === "function" ? handler(init) : handler;
    const hasBody = status !== 204 && body !== undefined;
    return new Response(hasBody ? JSON.stringify(body) : null, {
      status,
      headers: hasBody ? { "Content-Type": "application/json" } : undefined,
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const staffUser = { id: 1, username: "marie", email: "m@example.com", is_staff: true };
