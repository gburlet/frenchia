import { afterEach, describe, expect, it, vi } from "vitest";
import { sseResponse } from "./testUtils";
import { SseParser, streamTutor } from "./streamTutor";

afterEach(() => {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

function collect() {
  const events: [string, unknown][] = [];
  return {
    events,
    handlers: {
      onStart: (d: unknown) => events.push(["start", d]),
      onDelta: (d: unknown) => events.push(["delta", d]),
      onDone: (d: unknown) => events.push(["done", d]),
      onError: (d: unknown) => events.push(["error", d]),
    },
  };
}

const START = 'event: start\ndata: {"user_message_id": 10, "message_id": 11}\n\n';
const delta = (t: string) => `event: delta\ndata: ${JSON.stringify({ text: t })}\n\n`;
const DONE = 'event: done\ndata: {"message_id": 11, "status": "complete"}\n\n';

describe("SseParser", () => {
  it("parses frames split across chunks", () => {
    const p = new SseParser();
    expect(p.push("event: del")).toEqual([]);
    expect(p.push('ta\ndata: {"text":')).toEqual([]);
    expect(p.push(' "hi"}\n')).toEqual([]);
    expect(p.push("\n")).toEqual([{ event: "delta", data: '{"text": "hi"}' }]);
  });
  it("handles CRLF, comments, and a trailing unterminated frame", () => {
    const p = new SseParser();
    expect(p.push(": keepalive\r\n\r\nevent: delta\r\ndata: {}\r\n\r\n")).toEqual([{ event: "delta", data: "{}" }]);
    expect(p.push("event: done\ndata: {}")).toEqual([]);
    expect(p.flush()).toEqual([{ event: "done", data: "{}" }]);
  });
});

describe("streamTutor", () => {
  it("dispatches multiple events from one chunk", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => sseResponse([START + delta("Bec") + delta("ause ") + DONE])));
    const { events, handlers } = collect();
    await streamTutor("/api/x", { content: "hi" }, handlers);
    expect(events).toEqual([
      ["start", { user_message_id: 10, message_id: 11 }],
      ["delta", "Bec"],
      ["delta", "ause "],
      ["done", { message_id: 11, status: "complete" }],
    ]);
  });

  it("reassembles frames split mid-line across chunks", async () => {
    const all = START + delta("Hello") + DONE;
    const chunks = all.match(/[\s\S]{1,7}/g)!;
    vi.stubGlobal("fetch", vi.fn(async () => sseResponse(chunks)));
    const { events, handlers } = collect();
    await streamTutor("/api/x", {}, handlers);
    expect(events.map((e) => e[0])).toEqual(["start", "delta", "done"]);
    expect(events[1]![1]).toBe("Hello");
  });

  it("sends CSRF, JSON body and credentials", async () => {
    document.cookie = "csrftoken=tok; path=/";
    const fn = vi.fn(async () => sseResponse([DONE]));
    vi.stubGlobal("fetch", fn);
    await streamTutor("/api/x", { content: "a" }, {});
    const init = (fn.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-CSRFToken"]).toBe("tok");
    expect(JSON.parse(init.body as string)).toEqual({ content: "a" });
  });

  it("reports an error event", async () => {
    const err = 'event: error\ndata: {"message_id": 11, "code": "llm_unavailable", "detail": "Down."}\n\n';
    vi.stubGlobal("fetch", vi.fn(async () => sseResponse([START, err])));
    const { events, handlers } = collect();
    await streamTutor("/api/x", {}, handlers);
    expect(events[1]).toEqual(["error", { message_id: 11, code: "llm_unavailable", detail: "Down." }]);
    expect(events).toHaveLength(2);
  });

  it("reports a non-200 JSON error before streaming", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "Unknown thread." }), { status: 404, headers: { "Content-Type": "application/json" } })),
    );
    const { events, handlers } = collect();
    await streamTutor("/api/x", {}, handlers);
    expect(events).toEqual([["error", { message_id: null, code: "http_404", detail: "Unknown thread." }]]);
  });

  it("reports an interrupted stream", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => sseResponse([START, delta("x")])));
    const { events, handlers } = collect();
    await streamTutor("/api/x", {}, handlers);
    expect(events[events.length - 1]![0]).toBe("error");
    expect((events[events.length - 1]![1] as { code: string }).code).toBe("stream_interrupted");
  });

  it("reports a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const { events, handlers } = collect();
    await streamTutor("/api/x", {}, handlers);
    expect(events).toEqual([["error", { message_id: null, code: "network", detail: "Failed to fetch" }]]);
  });

  it("aborts quietly without calling onError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => sseResponse([START, delta("par")], { hang: true })));
    const { events, handlers } = collect();
    const controller = new AbortController();
    const done = streamTutor("/api/x", {}, { ...handlers, signal: controller.signal });
    await vi.waitFor(() => expect(events.some((e) => e[0] === "delta")).toBe(true));
    controller.abort();
    await done;
    expect(events.map((e) => e[0])).toEqual(["start", "delta"]);
  });
});
