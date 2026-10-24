import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { TutorDrawerContext } from "./TutorDrawerContext";

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
  );
}

export function TutorDrawerProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const toggle = useCallback(() => setOpen((value) => !value), []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "t" || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.defaultPrevented || isTypingTarget(event.target)) return;
      toggle();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle]);

  const value = useMemo(() => ({ open, setOpen, toggle }), [open, toggle]);
  return <TutorDrawerContext.Provider value={value}>{children}</TutorDrawerContext.Provider>;
}
