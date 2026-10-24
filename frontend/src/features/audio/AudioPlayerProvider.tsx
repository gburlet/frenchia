import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError } from "@/lib/api/client";
import { createAudio } from "@/lib/api/endpoints";
import { AudioPlayerContext, type AudioPlayer, type PlaybackState } from "./AudioPlayerContext";

function messageFor(error: unknown): string {
  if (error instanceof ApiError && error.status === 503) return "Speech is unavailable right now.";
  if (error instanceof ApiError) return error.detail;
  return "Could not play audio.";
}

/** Owns a single <audio> element so starting one clip stops any other. */
export function AudioPlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const requestRef = useRef(0);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [state, setState] = useState<PlaybackState>("idle");
  const [error, setError] = useState<string | null>(null);

  const audio = useCallback(() => {
    if (!audioRef.current) {
      const el = new Audio();
      el.addEventListener("ended", () => setState("idle"));
      audioRef.current = el;
    }
    return audioRef.current;
  }, []);

  useEffect(() => () => audioRef.current?.pause(), []);

  const stop = useCallback(() => {
    requestRef.current += 1;
    const el = audioRef.current;
    if (el) {
      el.pause();
      el.currentTime = 0;
    }
    setState("idle");
  }, []);

  const play = useCallback(
    async (id: string, text: string, speed = 1) => {
      stop();
      const request = requestRef.current;
      setActiveId(id);
      setError(null);
      setState("loading");
      try {
        const clip = await createAudio({ text, speed });
        if (request !== requestRef.current) return; // superseded by another play/stop
        const el = audio();
        el.src = clip.url;
        await el.play();
        if (request === requestRef.current) setState("playing");
      } catch (err) {
        if (request !== requestRef.current) return;
        setError(messageFor(err));
        setState("error");
      }
    },
    [audio, stop],
  );

  const value = useMemo<AudioPlayer>(
    () => ({ activeId, state, error, play, stop }),
    [activeId, state, error, play, stop],
  );
  return <AudioPlayerContext.Provider value={value}>{children}</AudioPlayerContext.Provider>;
}
