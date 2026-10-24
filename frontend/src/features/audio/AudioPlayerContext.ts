import { createContext, useContext } from "react";

export type PlaybackState = "idle" | "loading" | "playing" | "error";

export interface AudioPlayer {
  /** Id of the control that owns the current clip (one clip plays at a time). */
  activeId: string | null;
  state: PlaybackState;
  error: string | null;
  play: (id: string, text: string, speed?: number) => Promise<void>;
  stop: () => void;
}

export const AudioPlayerContext = createContext<AudioPlayer | null>(null);

export function useAudioPlayer(): AudioPlayer {
  const player = useContext(AudioPlayerContext);
  if (!player) throw new Error("useAudioPlayer must be used inside <AudioPlayerProvider>");
  return player;
}
