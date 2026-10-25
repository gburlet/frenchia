import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { Dialog } from "radix-ui";
import { X } from "lucide-react";
import { GO_TO, isTypingTarget, setShortcutsEnabled, shortcutsEnabled } from "./shortcuts";

const PAGE_KEYS: [string, string][] = [
  ["t", "Open or close the AI tutor"],
  ["Enter", "Check your answer (Shift+Enter for a new line)"],
  ["1–4", "Pick a multiple-choice option"],
  ["Space / Enter", "Flashcards: show the answer"],
  ["1–4", "Flashcards: Again, Hard, Good, Easy"],
];

function Kbd({ children }: { children: string }) {
  return <kbd className="rounded border border-line bg-chrome px-1.5 py-0.5 font-mono text-xs text-heading">{children}</kbd>;
}

/** "?" opens this list; "g" + a letter navigates. Mounted once in the app shell. */
export function ShortcutsDialog() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [enabled, setEnabled] = useState(shortcutsEnabled);
  const pendingGo = useRef<number | null>(null);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return;
      if (event.key === "?") {
        event.preventDefault();
        setOpen(true);
        return;
      }
      if (!shortcutsEnabled()) return;
      if (pendingGo.current !== null) {
        window.clearTimeout(pendingGo.current);
        pendingGo.current = null;
        const target = GO_TO.find((g) => g.key === event.key);
        if (target) {
          event.preventDefault();
          event.stopImmediatePropagation(); // e.g. "g t" must not also toggle the tutor
          void navigate(target.to);
        }
        return;
      }
      if (event.key === "g") {
        pendingGo.current = window.setTimeout(() => (pendingGo.current = null), 1500);
      }
    }
    // Capture phase: runs before the page's own window listeners.
    window.addEventListener("keydown", onKeyDown, { capture: true });
    return () => window.removeEventListener("keydown", onKeyDown, { capture: true });
  }, [navigate]);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger className="cursor-pointer text-sm text-muted underline hover:text-detail">
        Keyboard shortcuts <Kbd>?</Kbd>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-card bg-surface p-6 shadow-card">
          <div className="mb-4 flex items-start justify-between gap-4">
            <Dialog.Title className="text-2xl">Keyboard shortcuts</Dialog.Title>
            <Dialog.Close aria-label="Close" className="cursor-pointer rounded-control p-1 text-detail hover:text-heading">
              <X aria-hidden className="size-5" />
            </Dialog.Close>
          </div>
          <Dialog.Description className="mb-4 text-sm text-detail">
            Shortcuts work when you’re not typing in a text box.
          </Dialog.Description>
          <h3 className="mb-2 text-base">Go to</h3>
          <dl className="mb-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
            {GO_TO.map((g) => (
              <div key={g.key} className="contents">
                <dt>
                  <Kbd>g</Kbd> <Kbd>{g.key}</Kbd>
                </dt>
                <dd className="text-detail">{g.label}</dd>
              </div>
            ))}
          </dl>
          <h3 className="mb-2 text-base">On a page</h3>
          <dl className="mb-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
            {PAGE_KEYS.map(([key, label]) => (
              <div key={label} className="contents">
                <dt>
                  <Kbd>{key}</Kbd>
                </dt>
                <dd className="text-detail">{label}</dd>
              </div>
            ))}
          </dl>
          <label className="flex items-center gap-2 text-sm text-detail">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => {
                setShortcutsEnabled(e.target.checked);
                setEnabled(e.target.checked);
              }}
              className="accent-purple"
            />
            Single-key shortcuts (<Kbd>g</Kbd> and <Kbd>t</Kbd>) are on
          </label>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
