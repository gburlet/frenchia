import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { attemptResult } from "@/test/fixtures";
import { mockFetch } from "@/test/mockFetch";
import { renderWithProviders } from "@/test/renderCard";
import type { PublicExercise } from "@/lib/api/types";
import { ExerciseCard } from "./ExerciseCard";

const translate: PublicExercise = {
  exercise_revision_id: 42,
  id: "ex-05",
  type: "translate",
  direction: "en_fr",
  prompt: "I watched a movie last night.",
  hint: "regarder + film",
};
const fillBlank: PublicExercise = {
  exercise_revision_id: 41,
  id: "ex-04",
  type: "fill_blank",
  sentence: "Elle ___ à son ami.",
  hint: "(parler)",
  translation_en: "She spoke to her friend.",
};
const mcq: PublicExercise = {
  exercise_revision_id: 43,
  id: "ex-09",
  type: "multiple_choice",
  question: "Which is correct?",
  options: ["J’ai allé", "Je suis allé", "J’ai été", "Je vais allé"],
};
const comprehension: PublicExercise = {
  exercise_revision_id: 44,
  id: "ex-11",
  type: "comprehension",
  reading_id: "reading",
  question: "Who walked?",
  options: ["Marie", "Luc"],
};

const csrf = () => {
  document.cookie = "csrftoken=tok; path=/";
};
const attemptUrl = (rev: number) => `POST /api/exercise-revisions/${rev}/attempts`;
const bodyOf = (fn: ReturnType<typeof mockFetch>, match: string) => {
  const call = fn.mock.calls.find(([url]) => String(url).includes(match))!;
  return JSON.parse(call[1]!.body as string);
};

describe("ExerciseCard", () => {
  beforeEach(csrf);

  it("translate: shows spinner while the LLM works, then the result with errors", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const result = attemptResult({
      verdict: "incorrect",
      score: 40,
      grading: "llm",
      model: "gemma",
      feedback: {
        summary: "Close, but one slip.",
        errors: [{ category: "preposition", severity: "error", span: "à le", explanation: "Contract to au." }],
        corrected: "J’ai regardé un film hier soir.",
        register_note: "Casual register is fine.",
        accent_only: false,
      },
      correct_answer: "J’ai regardé un film hier soir.",
      accepted_answers: ["J’ai regardé un film hier soir.", "J’ai vu un film hier soir."],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        await gate;
        return new Response(JSON.stringify(result), { status: 200, headers: { "Content-Type": "application/json" } });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ExerciseCard exercise={translate} number={2} />);
    expect(screen.getByText("Translate into French")).toBeInTheDocument();
    const box = screen.getByRole("textbox", { name: "Your translation" });
    await user.type(box, "J’ai regardé à le film");
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText("Checking your answer…")).toBeInTheDocument();
    expect(box).toBeDisabled();
    release();
    const panel = await screen.findByTestId("result-panel");
    expect(within(panel).getByText("Incorrect")).toBeInTheDocument();
    expect(within(panel).getByText("Close, but one slip.")).toBeInTheDocument();
    expect(within(panel).getByText("preposition")).toBeInTheDocument();
    expect(within(panel).getByText("à le")).toHaveClass("text-error-text");
    expect(within(panel).getByText("Contract to au.")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: /Écouter : J’ai regardé un film/ })).toBeInTheDocument();
    expect(within(panel).getByText(/Accepted answers \(2\)/)).toBeInTheDocument();
    expect(within(panel).getByText("Casual register is fine.")).toBeInTheDocument();
    expect(within(panel).getByText("Feedback by the local AI tutor")).toBeInTheDocument();

    // Try again resets the card
    await user.click(within(panel).getByRole("button", { name: "Try again" }));
    expect(screen.queryByTestId("result-panel")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Your translation" })).toHaveValue("");
  });

  it("translate: Enter submits and Shift+Enter makes a newline; hint toggles", async () => {
    const fetchMock = mockFetch({ [attemptUrl(42)]: { body: attemptResult() } });
    const user = userEvent.setup();
    renderWithProviders(<ExerciseCard exercise={translate} />);
    const box = screen.getByRole("textbox", { name: "Your translation" });
    await user.type(box, "ligne un{Shift>}{Enter}{/Shift}ligne deux");
    expect(box).toHaveValue("ligne un\nligne deux");
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("attempts"))).toBe(false);
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Correct")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "attempts").answer).toBe("ligne un\nligne deux");
  });

  it("translate fr_en shows a speak button for the prompt and a hint toggle", async () => {
    mockFetch({});
    const user = userEvent.setup();
    renderWithProviders(
      <ExerciseCard exercise={{ ...translate, direction: "fr_en", prompt: "Il pleut." }} />,
    );
    expect(screen.getByText("Translate into English")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Écouter : Il pleut." })).toBeInTheDocument();
    expect(screen.queryByText("regarder + film")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show hint" }));
    expect(screen.getByText("regarder + film")).toBeInTheDocument();
  });

  it("fill_blank: inline input, helper translation, submit by Enter", async () => {
    const fetchMock = mockFetch({ [attemptUrl(41)]: { body: attemptResult() } });
    const user = userEvent.setup();
    renderWithProviders(<ExerciseCard exercise={fillBlank} />);
    expect(screen.getByText("(parler)", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("She spoke to her friend.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Missing word" }), "a parlé{Enter}");
    expect(await screen.findByText("Correct")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "attempts")).toMatchObject({ answer: "a parlé" });
    expect(screen.getByText("Bravo!")).toBeInTheDocument();
  });

  it("multiple_choice: number keys select, result highlights the correct index", async () => {
    const fetchMock = mockFetch({
      [attemptUrl(43)]: {
        body: attemptResult({
          verdict: "incorrect",
          correct_index: 1,
          correct_answer: "Je suis allé",
          explanation: "Aller takes être.",
          feedback: { summary: "Not quite.", errors: [], corrected: null, register_note: null, accent_only: false },
        }),
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<ExerciseCard exercise={mcq} />);
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    await user.click(screen.getAllByRole("radio")[0]!);
    await user.keyboard("3");
    expect(screen.getAllByRole("radio")[2]).toBeChecked();
    await user.keyboard("{Enter}");
    const panel = await screen.findByTestId("result-panel");
    expect(bodyOf(fetchMock, "attempts").answer).toBe(2);
    const items = within(panel).getAllByRole("listitem");
    expect(items[1]).toHaveAttribute("data-correct", "true");
    expect(within(items[2]!).getByText("Your choice")).toBeInTheDocument();
    expect(within(panel).getByText("Aller takes être.")).toBeInTheDocument();
    // MCQ cannot be disputed
    expect(screen.queryByRole("button", { name: /I think I’m right/ })).not.toBeInTheDocument();
  });

  it("comprehension links to the reading", () => {
    renderWithProviders(<ExerciseCard exercise={comprehension} />);
    expect(screen.getByRole("link", { name: "About the reading" })).toHaveAttribute("href", "#section-reading");
  });

  it("pending: shows reference answers and regrades on retry", async () => {
    const pending = attemptResult({
      status: "pending",
      verdict: null,
      score: null,
      grading: "pending",
      feedback: { summary: "The tutor is offline.", errors: [], corrected: null, register_note: null, accent_only: false },
    });
    const fetchMock = mockFetch({
      [attemptUrl(42)]: { body: pending },
      "POST /api/attempts/7/regrade": {
        body: attemptResult({ verdict: "acceptable", grading: "llm", feedback: { summary: "Fine.", errors: [], corrected: null, register_note: null, accent_only: false } }),
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<ExerciseCard exercise={translate} />);
    await user.type(screen.getByRole("textbox", { name: "Your translation" }), "x{Enter}");
    expect(await screen.findByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("The tutor is offline.")).toBeInTheDocument();
    expect(screen.getByText("Elle a parlé à son ami.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry automatic feedback" }));
    expect(await screen.findByText("Acceptable")).toBeInTheDocument();
    expect(screen.getByText("Fine.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/attempts/7/regrade")).toBe(true);
    expect(screen.queryByRole("button", { name: "Retry automatic feedback" })).not.toBeInTheDocument();
  });

  it("dispute: posts the comment and shows Sent for review", async () => {
    const fetchMock = mockFetch({
      [attemptUrl(41)]: { body: attemptResult({ verdict: "incorrect" }) },
      "POST /api/attempts/7/dispute": { body: { disputed: true } },
    });
    const user = userEvent.setup();
    renderWithProviders(<ExerciseCard exercise={fillBlank} />);
    await user.type(screen.getByRole("textbox", { name: "Missing word" }), "parla{Enter}");
    await user.click(await screen.findByRole("button", { name: "I think I’m right" }));
    await user.type(screen.getByLabelText("Comment (optional)"), "passé simple");
    await user.click(screen.getByRole("button", { name: "Send for review" }));
    expect(await screen.findByText("Sent for review")).toBeInTheDocument();
    await waitFor(() => expect(bodyOf(fetchMock, "dispute")).toEqual({ comment: "passé simple" }));
  });

  it("accent-only hint and register note render", async () => {
    mockFetch({
      [attemptUrl(41)]: {
        body: attemptResult({
          verdict: "acceptable",
          feedback: { summary: "Accents!", errors: [], corrected: null, register_note: "Informal.", accent_only: true },
        }),
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<ExerciseCard exercise={fillBlank} />);
    await user.type(screen.getByRole("textbox", { name: "Missing word" }), "a parle{Enter}");
    expect(await screen.findByText(/Only the accents differ/)).toBeInTheDocument();
    expect(screen.getByText("Informal.")).toBeInTheDocument();
  });
});
