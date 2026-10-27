import { useId } from "react";
import { Loader2, Square, Volume2, VolumeX } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAudioPlayer } from "./AudioPlayerContext";
import { stripBold } from "@/lib/sentences";

interface SpeakButtonProps {
  text: string;
  speed?: number;
  /** Accessible label; defaults to « Écouter : <text> ». */
  label?: string;
  className?: string;
}

/** Plays French text through the TTS service. Click again to stop. */
export function SpeakButton({ text, speed = 1, label, className }: SpeakButtonProps) {
  const id = useId();
  const player = useAudioPlayer();
  const state = player.activeId === id ? player.state : "idle";
  const busy = state === "loading" || state === "playing";
  const Icon = state === "loading" ? Loader2 : state === "playing" ? Square : state === "error" ? VolumeX : Volume2;

  return (
    <button
      type="button"
      onClick={() => (busy ? player.stop() : void player.play(id, text, speed))}
      aria-label={busy ? "Arrêter la lecture" : (label ?? `Écouter : ${stripBold(text)}`)}
      aria-pressed={state === "playing"}
      title={state === "error" ? (player.error ?? undefined) : undefined}
      className={cn(
        "inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full text-teal transition-[background-color,transform] duration-200 ease-in-out hover:scale-[1.04] hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple motion-reduce:transition-none motion-reduce:hover:scale-100",
        state === "error" && "text-error-text",
        className,
      )}
    >
      <Icon aria-hidden className={cn("size-5", state === "loading" && "animate-spin motion-reduce:animate-none")} />
    </button>
  );
}
