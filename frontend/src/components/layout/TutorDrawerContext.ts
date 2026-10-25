import { createContext, useContext, useEffect, useId } from "react";
import type { TutorChat } from "@/features/tutor/useTutorChat";
import type { TutorContextInfo, TutorContextRef } from "@/features/tutor/types";

export type { TutorContextRef } from "@/features/tutor/types";

export interface OpenTutorOptions {
  prompt?: string;
  /** Send the prompt immediately (default) or only pre-fill the input. */
  send?: boolean;
}

export interface TutorDrawerValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  openTutor: (options?: OpenTutorOptions) => void;
  /** Most specific registered context. */
  context: TutorContextInfo;
  registerContext: (key: string, ref: TutorContextRef, label: string) => void;
  unregisterContext: (key: string) => void;
  chat: TutorChat;
}

export const TutorDrawerContext = createContext<TutorDrawerValue | null>(null);

export function useTutorDrawer(): TutorDrawerValue {
  const value = useContext(TutorDrawerContext);
  if (!value) throw new Error("useTutorDrawer must be used within TutorDrawerProvider");
  return value;
}

/** Opens the drawer; a no-op outside the provider so isolated components still render. */
export function useOpenTutor(): (options?: OpenTutorOptions) => void {
  return useContext(TutorDrawerContext)?.openTutor ?? noop;
}
function noop() {
  /* no tutor mounted */
}

/**
 * Declares what is in view. The most specific registration wins (exercise > lesson);
 * among equals the most recently registered/activated wins. Pass `null` to not register.
 * Bump `activation` to make an already-registered context the most recent again.
 */
export function useTutorContext(ref: TutorContextRef | null, label: string, activation = 0): void {
  const ctx = useContext(TutorDrawerContext);
  const key = useId();
  const register = ctx?.registerContext;
  const unregister = ctx?.unregisterContext;
  const active = ref !== null;
  const lessonId = ref?.lesson_id;
  const revisionId = ref?.exercise_revision_id;
  const attemptId = ref?.attempt_id;

  useEffect(() => {
    if (!register || !unregister || !active) return;
    const next: TutorContextRef = {};
    if (lessonId !== undefined) next.lesson_id = lessonId;
    if (revisionId !== undefined) next.exercise_revision_id = revisionId;
    if (attemptId !== undefined) next.attempt_id = attemptId;
    register(key, next, label);
    return () => unregister(key);
  }, [register, unregister, key, active, lessonId, revisionId, attemptId, label, activation]);
}
