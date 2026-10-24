import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockFetch } from "@/test/mockFetch";
import { AudioPlayerProvider } from "./AudioPlayerProvider";
import { SpeakButton } from "./SpeakButton";

function renderButtons() {
  render(
    <AudioPlayerProvider>
      <SpeakButton text="Bonjour" label="Écouter bonjour" />
      <SpeakButton text="Salut" speed={0.75} label="Écouter salut" />
    </AudioPlayerProvider>,
  );
}

describe("SpeakButton", () => {
  let play: ReturnType<typeof vi.fn<() => Promise<void>>>;

  beforeEach(() => {
    // Restore here, not in afterEach: React unmounts after afterEach hooks and calls pause().
    vi.restoreAllMocks();
    document.cookie = "csrftoken=tok";
    play = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(play);
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  });

  it("requests audio and plays it", async () => {
    const fetchMock = mockFetch({
      "POST /api/audio": { body: { key: "k1", url: "/api/audio/k1.wav", cached: false } },
    });
    renderButtons();
    await userEvent.click(screen.getByRole("button", { name: "Écouter salut" }));
    expect(await screen.findByRole("button", { name: "Arrêter la lecture" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(play).toHaveBeenCalledOnce();
    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(init!.body as string)).toEqual({ text: "Salut", speed: 0.75 });
  });

  it("clicking while playing stops playback", async () => {
    mockFetch({ "POST /api/audio": { body: { key: "k1", url: "/api/audio/k1.wav", cached: true } } });
    renderButtons();
    await userEvent.click(screen.getByRole("button", { name: "Écouter bonjour" }));
    await userEvent.click(await screen.findByRole("button", { name: "Arrêter la lecture" }));
    expect(screen.getByRole("button", { name: "Écouter bonjour" })).toHaveAttribute("aria-pressed", "false");
  });

  it("shows unavailable speech without throwing", async () => {
    mockFetch({
      "POST /api/audio": { status: 503, body: { detail: "down", code: "tts_unavailable" } },
    });
    renderButtons();
    await userEvent.click(screen.getByRole("button", { name: "Écouter bonjour" }));
    expect(await screen.findByTitle("Speech is unavailable right now.")).toBeInTheDocument();
    expect(play).not.toHaveBeenCalled();
  });
});
