import { useEffect, useRef, type KeyboardEvent } from "react";
import { MessageSquarePlus, Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SheetTitle } from "@/components/ui/sheet";
import { useTutorDrawer } from "@/components/layout/TutorDrawerContext";
import { Markdown } from "@/features/lessons/Markdown";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "./types";

const QUICK_PROMPTS = {
  wrong: "Why is my answer wrong?",
  rule: "Explain the rule",
  examples: "Give me 3 more examples",
  quebec: "How would someone in Québec say this?",
  imparfait: "Can I use the imparfait instead?",
} as const;

function Caret() {
  return (
    <span
      aria-hidden
      data-testid="tutor-caret"
      className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-[caret-blink_1s_steps(1)_infinite] bg-purple motion-reduce:animate-none"
    />
  );
}

function AssistantMessage({ message, onRetry, disabled }: { message: ChatMessage; onRetry: () => void; disabled: boolean }) {
  const streaming = message.status === "streaming";
  return (
    <div className="flex max-w-full flex-col items-start gap-1" data-status={message.status}>
      <span className="text-[0.7rem] text-muted">Local AI tutor</span>
      <div className="max-w-full text-sm text-body">
        {message.content && <Markdown className="[&>div>:first-child]:mt-0 [&>div>:last-child]:mb-0">{message.content}</Markdown>}
        {streaming && <Caret />}
      </div>
      {message.status === "stopped" && (
        <p className="flex items-center gap-2 text-xs text-muted">
          Stopped
          <button type="button" disabled={disabled} onClick={onRetry} className="cursor-pointer text-teal underline disabled:opacity-60">
            Regenerate
          </button>
        </p>
      )}
      {message.status === "error" && (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-sm text-error-text">
          <span>{message.error ?? "Something went wrong."}</span>
          <Button type="button" variant="ghost" className="h-7 px-3 text-xs" disabled={disabled} onClick={onRetry}>
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}

export function TutorPanel() {
  const { context, chat } = useTutorDrawer();
  const { items, streaming, loading, draft, setDraft, send, stop, retry, newConversation } = chat;
  const listRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  const { ref } = context;
  const prompts: string[] = [
    ...(ref.attempt_id !== undefined ? [QUICK_PROMPTS.wrong] : []),
    QUICK_PROMPTS.rule,
    QUICK_PROMPTS.examples,
    QUICK_PROMPTS.quebec,
    ...(ref.lesson_id !== undefined ? [QUICK_PROMPTS.imparfait] : []),
  ];

  useEffect(() => {
    const el = listRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [items]);

  function onScroll() {
    const el = listRef.current;
    if (!el) return;
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  }

  function submit(text: string) {
    if (streaming || !text.trim()) return;
    stickRef.current = true;
    void send(text);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit(draft);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex flex-col gap-2 border-b border-line px-4 py-4 pr-12">
        <div className="flex items-center justify-between gap-2">
          <SheetTitle>Tuteur</SheetTitle>
          <Button type="button" variant="ghost" className="h-8 gap-1 px-3 text-xs" onClick={newConversation}>
            <MessageSquarePlus aria-hidden className="size-3.5" />
            New conversation
          </Button>
        </div>
        <p
          data-testid="tutor-context"
          className="w-fit max-w-full truncate rounded-full border border-line bg-chrome px-3 py-1 text-xs text-detail"
        >
          {context.label ? `About: ${context.label}` : "General"}
        </p>
      </header>

      <div ref={listRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div aria-live="polite" aria-busy={streaming} className="flex flex-col gap-4">
          {loading && <p className="text-sm text-muted">Loading conversation…</p>}
          {!loading && items.length === 0 && (
            <p className="text-sm text-detail">
              Ask about what’s on your screen: a rule, a mistake, or how it’s said in Québec.
            </p>
          )}
          {items.map((item) => {
            if (item.kind === "divider") {
              return (
                <div key={item.localId} role="separator" className="flex items-center gap-2 text-xs text-muted">
                  <span className="h-px flex-1 bg-line" />
                  <span>{item.label}</span>
                  <span className="h-px flex-1 bg-line" />
                </div>
              );
            }
            if (item.role === "user") {
              return (
                <div key={item.localId} className="flex justify-end">
                  <p className="max-w-[85%] whitespace-pre-wrap rounded-card bg-chrome px-3 py-2 text-sm text-heading">{item.content}</p>
                </div>
              );
            }
            return (
              <AssistantMessage
                key={item.localId}
                message={item}
                disabled={streaming}
                onRetry={() => void retry(item.localId)}
              />
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2 border-t border-line px-4 py-3">
        {draft.length === 0 && (
          <div className="flex flex-wrap gap-2" role="group" aria-label="Quick prompts">
            {prompts.map((p) => (
              <button
                key={p}
                type="button"
                disabled={streaming}
                onClick={() => submit(p)}
                className={cn(
                  "cursor-pointer rounded-full border border-line bg-chrome px-3 py-1 text-xs text-detail transition-colors duration-200 hover:border-purple hover:text-heading",
                  "disabled:cursor-not-allowed disabled:opacity-60",
                )}
              >
                {p}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <label htmlFor="tutor-input" className="sr-only">
            Message the tutor
          </label>
          <textarea
            id="tutor-input"
            data-tutor-input
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask the tutor (Enter to send, Shift+Enter for a new line)"
            className="max-h-40 min-h-[3.25rem] flex-1 resize-none rounded-control border border-line bg-chrome p-2 text-sm text-heading placeholder:text-muted focus-visible:border-purple"
          />
          {streaming ? (
            <Button type="button" variant="ghost" onClick={stop} className="gap-1">
              <Square aria-hidden className="size-3.5" />
              Stop
            </Button>
          ) : (
            <Button type="button" onClick={() => submit(draft)} disabled={!draft.trim()} className="h-[38px] gap-1 px-4 text-[0.9rem]">
              <Send aria-hidden className="size-3.5" />
              Send
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
