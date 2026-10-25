import { ensureCsrfCookie } from "@/lib/api/client";

export interface TutorStreamStart {
  user_message_id?: number;
  message_id: number;
}
export interface TutorStreamDone {
  message_id: number;
  status: "complete" | "stopped" | "error" | (string & {});
}
export interface TutorStreamError {
  message_id: number | null;
  code: string;
  detail: string;
}

export interface TutorStreamHandlers {
  onStart?: (data: TutorStreamStart) => void;
  onDelta?: (text: string) => void;
  onDone?: (data: TutorStreamDone) => void;
  onError?: (error: TutorStreamError) => void;
  signal?: AbortSignal;
}

export interface SseFrame {
  event: string;
  data: string;
}

/** Incremental SSE parser: feed text chunks, get complete frames. */
export class SseParser {
  private buffer = "";

  push(chunk: string): SseFrame[] {
    this.buffer += chunk;
    this.buffer = this.buffer.replace(/\r\n?/g, "\n");
    const frames: SseFrame[] = [];
    let index: number;
    while ((index = this.buffer.indexOf("\n\n")) !== -1) {
      const raw = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 2);
      const frame = parseFrame(raw);
      if (frame) frames.push(frame);
    }
    return frames;
  }

  /** Emit a trailing frame that was not terminated by a blank line. */
  flush(): SseFrame[] {
    const raw = this.buffer;
    this.buffer = "";
    const frame = raw.trim() ? parseFrame(raw) : null;
    return frame ? [frame] : [];
  }
}

function parseFrame(raw: string): SseFrame | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n") };
}

function safeJson(text: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(text);
    return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/**
 * POSTs to a tutor streaming endpoint and dispatches SSE events to the handlers.
 * Resolves when the stream ends. An abort resolves quietly without calling onError
 * (the caller knows it aborted). Failures are reported through onError, never thrown.
 */
export async function streamTutor(
  url: string,
  body: unknown,
  { onStart, onDelta, onDone, onError, signal }: TutorStreamHandlers = {},
): Promise<void> {
  const fail = (error: TutorStreamError) => {
    if (!signal?.aborted) onError?.(error);
  };
  let settled = false;

  try {
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const token = await ensureCsrfCookie();
    if (token) headers["X-CSRFToken"] = token;

    const response = await fetch(url, {
      method: "POST",
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      const json = safeJson(text);
      const detail = typeof json?.detail === "string" ? json.detail : response.statusText || `Request failed (${response.status})`;
      fail({ message_id: null, code: `http_${response.status}`, detail });
      return;
    }
    if (!response.body) {
      fail({ message_id: null, code: "no_body", detail: "The tutor sent an empty response." });
      return;
    }

    const reader = response.body.getReader();
    const onAbort = () => void reader.cancel().catch(() => undefined);
    signal?.addEventListener("abort", onAbort);
    const decoder = new TextDecoder();
    const parser = new SseParser();

    const dispatch = (frame: SseFrame) => {
      const data = safeJson(frame.data);
      if (!data) return;
      if (frame.event === "start") onStart?.(data as unknown as TutorStreamStart);
      else if (frame.event === "delta") {
        if (typeof data.text === "string") onDelta?.(data.text);
      } else if (frame.event === "done") {
        settled = true;
        onDone?.(data as unknown as TutorStreamDone);
      } else if (frame.event === "error") {
        settled = true;
        onError?.({
          message_id: typeof data.message_id === "number" ? data.message_id : null,
          code: typeof data.code === "string" ? data.code : "error",
          detail: typeof data.detail === "string" ? data.detail : "Something went wrong.",
        });
      }
    };

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (signal?.aborted) return;
        if (done) break;
        for (const frame of parser.push(decoder.decode(value, { stream: true }))) dispatch(frame);
      }
      for (const frame of parser.push(decoder.decode())) dispatch(frame);
      for (const frame of parser.flush()) dispatch(frame);
    } finally {
      signal?.removeEventListener("abort", onAbort);
    }

    if (!settled && !signal?.aborted) {
      fail({ message_id: null, code: "stream_interrupted", detail: "The connection to the tutor was interrupted." });
    }
  } catch (error) {
    if (signal?.aborted) return;
    fail({
      message_id: null,
      code: "network",
      detail: error instanceof Error && error.message ? error.message : "Couldn’t reach the tutor.",
    });
  }
}
