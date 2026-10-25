import type { RefObject } from "react";
import { cn } from "@/lib/utils";

const KEYS = ["é", "è", "ê", "à", "â", "ç", "ù", "û", "ô", "î", "ë", "ï", "œ"];

interface AccentKeysProps {
  /** The input or textarea the characters are inserted into, at the caret. */
  target: RefObject<HTMLInputElement | HTMLTextAreaElement | null>;
  /** Called with the new value (for controlled inputs). */
  onInsert: (value: string) => void;
  className?: string;
  disabled?: boolean;
}

/** A row of buttons for French characters that are awkward to type on an English keyboard. */
export function AccentKeys({ target, onInsert, className, disabled }: AccentKeysProps) {
  const insert = (char: string) => {
    const el = target.current;
    if (!el) return;
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const value = el.value.slice(0, start) + char + el.value.slice(end);
    onInsert(value);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + char.length, start + char.length);
    });
  };
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)} role="group" aria-label="Accented letters">
      {KEYS.map((char) => (
        <button
          key={char}
          type="button"
          disabled={disabled}
          // Keep focus (and the caret) in the input.
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => insert(char)}
          aria-label={`Insert ${char}`}
          className="min-w-8 cursor-pointer rounded-md border border-white/10 px-2 py-1 text-sm text-white/90 transition-colors hover:border-teal hover:text-teal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple disabled:cursor-not-allowed disabled:opacity-50"
        >
          {char}
        </button>
      ))}
    </div>
  );
}
