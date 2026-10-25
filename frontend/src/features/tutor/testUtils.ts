/** Test helper: a streaming SSE Response. With `hang`, the stream stays open until cancelled. */
export function sseResponse(chunks: string[], { hang = false, status = 200 }: { hang?: boolean; status?: number } = {}): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      if (!hang) controller.close();
    },
  });
  return new Response(stream, { status, headers: { "Content-Type": "text/event-stream" } });
}

/** A hand-driven SSE response: push chunks over time, then close. */
export function controlledSse() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    response: () => new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    push: (text: string) => controller.enqueue(encoder.encode(text)),
    close: () => controller.close(),
  };
}

export const sse = {
  start: (messageId = 11) => `event: start\ndata: ${JSON.stringify({ user_message_id: messageId - 1, message_id: messageId })}\n\n`,
  delta: (text: string) => `event: delta\ndata: ${JSON.stringify({ text })}\n\n`,
  done: (messageId = 11, status = "complete") => `event: done\ndata: ${JSON.stringify({ message_id: messageId, status })}\n\n`,
  error: (messageId = 11, detail = "The local AI tutor isn't running.") =>
    `event: error\ndata: ${JSON.stringify({ message_id: messageId, code: "llm_unavailable", detail })}\n\n`,
};

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
