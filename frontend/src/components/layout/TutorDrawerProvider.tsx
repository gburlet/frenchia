import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTutorChat } from "@/features/tutor/useTutorChat";
import type { TutorContextInfo, TutorContextRef } from "@/features/tutor/types";
import { isTypingTarget, shortcutsEnabled } from "./shortcuts";
import { TutorDrawerContext, type OpenTutorOptions } from "./TutorDrawerContext";


interface Registration {
  key: string;
  ref: TutorContextRef;
  label: string;
  seq: number;
}

const EMPTY: TutorContextInfo = { ref: {}, label: "" };

function specificity(ref: TutorContextRef): number {
  if (ref.attempt_id !== undefined || ref.exercise_revision_id !== undefined) return 2;
  return ref.lesson_id !== undefined ? 1 : 0;
}

export function TutorDrawerProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const toggle = useCallback(() => setOpen((value) => !value), []);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const seq = useRef(0);

  const registerContext = useCallback((key: string, ref: TutorContextRef, label: string) => {
    seq.current += 1;
    const entry = { key, ref, label, seq: seq.current };
    setRegistrations((prev) => [...prev.filter((r) => r.key !== key), entry]);
  }, []);
  const unregisterContext = useCallback((key: string) => {
    setRegistrations((prev) => (prev.some((r) => r.key === key) ? prev.filter((r) => r.key !== key) : prev));
  }, []);

  const context = useMemo<TutorContextInfo>(() => {
    let best: Registration | null = null;
    for (const r of registrations) {
      if (!best || specificity(r.ref) > specificity(best.ref) || (specificity(r.ref) === specificity(best.ref) && r.seq > best.seq)) {
        best = r;
      }
    }
    return best ? { ref: best.ref, label: best.label } : EMPTY;
  }, [registrations]);

  const contextRef = useRef(context);
  useEffect(() => {
    contextRef.current = context;
  }, [context]);

  const chat = useTutorChat(contextRef);
  const { send, setDraft, hydrate } = chat;

  useEffect(() => {
    if (open) void hydrate();
  }, [open, hydrate]);

  const openTutor = useCallback(
    ({ prompt, send: autoSend = true }: OpenTutorOptions = {}) => {
      setOpen(true);
      if (!prompt) return;
      if (autoSend) void send(prompt);
      else setDraft(prompt);
    },
    [send, setDraft],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "t" || event.ctrlKey || event.metaKey || event.altKey || !shortcutsEnabled()) return;
      if (event.defaultPrevented || isTypingTarget(event.target)) return;
      toggle();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle]);

  const value = useMemo(
    () => ({ open, setOpen, toggle, openTutor, context, registerContext, unregisterContext, chat }),
    [open, toggle, openTutor, context, registerContext, unregisterContext, chat],
  );
  return <TutorDrawerContext.Provider value={value}>{children}</TutorDrawerContext.Provider>;
}
