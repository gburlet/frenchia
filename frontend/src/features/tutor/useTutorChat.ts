import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { api } from "@/lib/api/client";
import { streamTutor } from "./streamTutor";
import {
  contextKey,
  type ChatItem,
  type ChatMessage,
  type ThreadDetail,
  type ThreadId,
  type TutorContextInfo,
} from "./types";

const STORAGE_KEY = "frenchia.tutor.thread";

function readStoredThread(): ThreadId | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ThreadId) : null;
  } catch {
    return null;
  }
}
function storeThread(id: ThreadId | null) {
  try {
    if (id === null) sessionStorage.removeItem(STORAGE_KEY);
    else sessionStorage.setItem(STORAGE_KEY, JSON.stringify(id));
  } catch {
    /* storage unavailable */
  }
}

let counter = 0;
const nextId = () => `local-${++counter}`;

export interface TutorChat {
  items: ChatItem[];
  streaming: boolean;
  threadId: ThreadId | null;
  loading: boolean;
  draft: string;
  setDraft: (value: string) => void;
  send: (content: string) => Promise<void>;
  stop: () => void;
  retry: (localId: string) => Promise<void>;
  newConversation: () => void;
  /** Loads the persisted thread once (no-op when there is none). */
  hydrate: () => Promise<void>;
}

export function useTutorChat(contextRef: RefObject<TutorContextInfo>): TutorChat {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState("");
  const [threadId, setThreadIdState] = useState<ThreadId | null>(readStoredThread);

  const threadIdRef = useRef<ThreadId | null>(threadId);
  const sentContextRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamingRef = useRef(false);
  const hydrationRef = useRef<Promise<void> | null>(null);
  const itemsRef = useRef<ChatItem[]>([]);

  const updateItems = useCallback((fn: (prev: ChatItem[]) => ChatItem[]) => {
    itemsRef.current = fn(itemsRef.current);
    setItems(itemsRef.current);
  }, []);

  const setThread = useCallback((id: ThreadId | null) => {
    threadIdRef.current = id;
    setThreadIdState(id);
    storeThread(id);
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  const hydrate = useCallback((): Promise<void> => {
    if (hydrationRef.current) return hydrationRef.current;
    const id = threadIdRef.current;
    if (id === null) {
      hydrationRef.current = Promise.resolve();
      return hydrationRef.current;
    }
    setLoading(true);
    hydrationRef.current = api
      .get<ThreadDetail>(`/api/tutor/threads/${id}`)
      .then((thread) => {
        if (threadIdRef.current !== id) return;
        sentContextRef.current = contextKey(thread.context ?? {});
        updateItems(() =>
          thread.messages.map<ChatMessage>((m) => ({
            kind: "message",
            localId: nextId(),
            serverId: m.id,
            role: m.role,
            content: m.content,
            status: m.status,
            error: m.status === "error" ? "This reply failed." : undefined,
          })),
        );
      })
      .catch(() => {
        // Unknown or unreachable thread: start fresh.
        if (threadIdRef.current === id) setThread(null);
      })
      .finally(() => setLoading(false));
    return hydrationRef.current;
  }, [setThread, updateItems]);

  const runStream = useCallback(
    async (assistantId: string, resolveRequest: () => Promise<{ url: string; body?: unknown }>) => {
      const controller = new AbortController();
      abortRef.current = controller;
      streamingRef.current = true;
      setStreaming(true);
      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        updateItems((prev) => prev.map((i) => (i.kind === "message" && i.localId === assistantId ? fn(i) : i)));
      try {
        let request: { url: string; body?: unknown };
        try {
          request = await resolveRequest();
        } catch (error) {
          patch((m) => ({ ...m, status: "error", error: error instanceof Error ? error.message : "Couldn’t reach the tutor." }));
          return;
        }
        if (controller.signal.aborted) {
          patch((m) => ({ ...m, status: "stopped" }));
          return;
        }
        await streamTutor(request.url, request.body, {
          signal: controller.signal,
          onStart: ({ message_id }) => patch((m) => ({ ...m, serverId: message_id })),
          onDelta: (text) => patch((m) => ({ ...m, content: m.content + text })),
          onDone: ({ status }) => patch((m) => ({ ...m, status: status === "stopped" ? "stopped" : status === "error" ? "error" : "complete" })),
          onError: (e) => patch((m) => ({ ...m, status: "error", error: e.detail, serverId: e.message_id ?? m.serverId })),
        });
        if (controller.signal.aborted) patch((m) => (m.status === "streaming" ? { ...m, status: "stopped" } : m));
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        streamingRef.current = false;
        setStreaming(false);
      }
    },
    [updateItems],
  );

  const send = useCallback(
    async (raw: string) => {
      const content = raw.trim();
      if (!content || streamingRef.current) return;
      streamingRef.current = true; // block re-entrancy while hydrating
      await hydrate();
      const ctx = contextRef.current;
      const key = contextKey(ctx.ref);
      const changed = threadIdRef.current !== null && sentContextRef.current !== key;

      const assistantId = nextId();
      updateItems((prev) => [
        ...prev,
        ...(changed
          ? [{ kind: "divider" as const, localId: nextId(), label: `Now about: ${ctx.label || "General"}` }]
          : []),
        { kind: "message", localId: nextId(), role: "user", content, status: "complete" },
        { kind: "message", localId: assistantId, role: "assistant", content: "", status: "streaming", retryContent: content },
      ]);
      setDraft("");

      await runStream(assistantId, async () => {
        let id = threadIdRef.current;
        if (id === null) {
          const created = await api.post<{ id: ThreadId }>("/api/tutor/threads", { context: ctx.ref });
          id = created.id;
          setThread(id);
        }
        sentContextRef.current = key;
        return {
          url: `/api/tutor/threads/${id}/messages`,
          body: changed ? { content, context: ctx.ref } : { content },
        };
      });
    },
    [contextRef, hydrate, runStream, setThread, updateItems],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const retry = useCallback(
    async (localId: string) => {
      if (streamingRef.current) return;
      const index = itemsRef.current.findIndex((i) => i.localId === localId);
      const message = itemsRef.current[index];
      if (!message || message.kind !== "message") return;
      if (message.serverId === undefined) {
        // The server never created the reply: drop the failed pair and send again.
        const content = message.retryContent;
        if (!content) return;
        updateItems((prev) => prev.filter((_, i) => i !== index && i !== index - 1));
        await send(content);
        return;
      }
      const serverId = message.serverId;
      updateItems((prev) =>
        prev.map((i) => (i.localId === localId && i.kind === "message" ? { ...i, content: "", status: "streaming", error: undefined } : i)),
      );
      await runStream(localId, async () => ({ url: `/api/tutor/messages/${serverId}/retry` }));
    },
    [runStream, send, updateItems],
  );

  const newConversation = useCallback(() => {
    abortRef.current?.abort();
    hydrationRef.current = Promise.resolve();
    sentContextRef.current = null;
    setThread(null);
    updateItems(() => []);
    setDraft("");
    setLoading(false);
  }, [setThread, updateItems]);

  return { items, streaming, threadId, loading, draft, setDraft, send, stop, retry, newConversation, hydrate };
}
