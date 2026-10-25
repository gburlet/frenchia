/** Single-character shortcuts can be switched off (WCAG 2.1.4); this is a per-browser setting. */
const STORAGE_KEY = "frenchia.shortcuts";

export function shortcutsEnabled(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

export function setShortcutsEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, enabled ? "on" : "off");
  } catch {
    /* private mode: the setting just doesn't persist */
  }
}

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/** "g" then a letter. */
export const GO_TO: { key: string; to: string; label: string }[] = [
  { key: "d", to: "/", label: "Dashboard" },
  { key: "c", to: "/curriculum", label: "Curriculum" },
  { key: "r", to: "/practice/review", label: "Review" },
  { key: "s", to: "/practice/translate", label: "Translation Station" },
  { key: "v", to: "/practice/verbs", label: "Verb Station" },
  { key: "w", to: "/practice/vocab", label: "Vocabulary (words)" },
  { key: "f", to: "/practice/vocab/review", label: "Flashcard review" },
  { key: "p", to: "/progress", label: "Progress" },
];
