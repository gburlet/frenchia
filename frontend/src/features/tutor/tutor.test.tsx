import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TutorDrawer } from "@/components/layout/TutorDrawer";
import { TutorDrawerProvider } from "@/components/layout/TutorDrawerProvider";
import { useTutorContext, type TutorContextRef } from "@/components/layout/TutorDrawerContext";
import { ExerciseCard } from "@/features/exercises/ExerciseCard";
import type { PublicExercise } from "@/lib/api/types";
import { attemptResult } from "@/test/fixtures";
import { renderWithProviders } from "@/test/renderCard";
import { controlledSse, jsonResponse, sse, sseResponse } from "./testUtils";

type Handler = (init: RequestInit) => Response | Promise<Response>;

/** Routes "METHOD /path" to handlers; records every call. */
function route(table: Record<string, Handler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const key = `${(init.method ?? "GET").toUpperCase()} ${String(input)}`;
    const handler = table[key];
    if (!handler) throw new Error(`Unmocked request: ${key}`);
    return handler(init);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
const bodies = (fn: ReturnType<typeof route>, key: string) =>
  fn.mock.calls
    .filter(([url, init]) => `${(init?.method ?? "GET").toUpperCase()} ${String(url)}` === key)
    .map(([, init]) => JSON.parse(String(init?.body)));

const thread = (id = 5) => () => jsonResponse({ id, title: "t", context: {}, messages: [] }, 201);

function Register({ refValue, label }: { refValue: TutorContextRef; label: string }) {
  useTutorContext(refValue, label);
  return null;
}

let setExercise: (v: boolean) => void = () => undefined;
function Harness({ lesson = true }: { lesson?: boolean }) {
  const [exercise, set] = useState(false);
  useEffect(() => {
    setExercise = set;
  }, []);
  return (
    <TutorDrawerProvider>
      {lesson && <Register refValue={{ lesson_id: "a2-imparfait" }} label="L'imparfait" />}
      {exercise && (
        <Register
          refValue={{ lesson_id: "a2-imparfait", exercise_revision_id: 41, attempt_id: 7 }}
          label="Exercise 4 · L'imparfait"
        />
      )}
      <TutorDrawer />
    </TutorDrawerProvider>
  );
}

async function openDrawer() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Tuteur" }));
  const dialog = await screen.findByRole("dialog");
  return { user, dialog };
}
const input = () => screen.getByLabelText("Message the tutor");

beforeEach(() => {
  document.cookie = "csrftoken=tok; path=/";
});

describe("tutor drawer", () => {
  it("shows the most specific registered context and updates when an exercise registers", async () => {
    renderWithProviders(<Harness />);
    const { dialog } = await openDrawer();
    expect(within(dialog).getByTestId("tutor-context")).toHaveTextContent("About: L'imparfait");
    act(() => setExercise(true));
    expect(within(dialog).getByTestId("tutor-context")).toHaveTextContent("About: Exercise 4 · L'imparfait");
    act(() => setExercise(false));
    expect(within(dialog).getByTestId("tutor-context")).toHaveTextContent("About: L'imparfait");
  });

  it("says General without context and hides context-only quick prompts", async () => {
    renderWithProviders(<Harness lesson={false} />);
    const { dialog } = await openDrawer();
    expect(within(dialog).getByTestId("tutor-context")).toHaveTextContent("General");
    expect(within(dialog).getByRole("button", { name: "Explain the rule" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Why is my answer wrong?" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Can I use the imparfait instead?" })).not.toBeInTheDocument();
  });

  it("offers attempt and lesson prompts when in context", async () => {
    renderWithProviders(<Harness />);
    const { dialog } = await openDrawer();
    expect(within(dialog).getByRole("button", { name: "Can I use the imparfait instead?" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Why is my answer wrong?" })).not.toBeInTheDocument();
    act(() => setExercise(true));
    expect(within(dialog).getByRole("button", { name: "Why is my answer wrong?" })).toBeInTheDocument();
  });

  it("sends a quick prompt immediately, creating a thread with the context first", async () => {
    const fn = route({
      "POST /api/tutor/threads": thread(),
      "POST /api/tutor/threads/5/messages": () => sseResponse([sse.start(), sse.delta("Rule: "), sse.done()]),
    });
    renderWithProviders(<Harness />);
    const { user, dialog } = await openDrawer();
    await user.click(within(dialog).getByRole("button", { name: "Explain the rule" }));
    expect(await within(dialog).findByText(/Rule:/)).toBeInTheDocument();
    expect(within(dialog).getAllByText("Explain the rule").length).toBeGreaterThan(1);
    expect(bodies(fn, "POST /api/tutor/threads")).toEqual([{ context: { lesson_id: "a2-imparfait" } }]);
    expect(bodies(fn, "POST /api/tutor/threads/5/messages")).toEqual([{ content: "Explain the rule" }]);
    expect(sessionStorage.getItem("frenchia.tutor.thread")).toBe("5");
    expect(within(dialog).getByText("Local AI tutor")).toBeInTheDocument();
  });

  it("streams deltas into the message with a caret, then settles", async () => {
    const s = controlledSse();
    route({ "POST /api/tutor/threads": thread(), "POST /api/tutor/threads/5/messages": () => s.response() });
    renderWithProviders(<Harness />);
    const { user, dialog } = await openDrawer();
    await user.type(input(), "Hello{Enter}");
    await within(dialog).findByRole("button", { name: "Stop" });
    await waitFor(() => expect(within(dialog).getByTestId("tutor-caret")).toBeInTheDocument());
    act(() => s.push(sse.start() + sse.delta("Because ")));
    expect(await within(dialog).findByText("Because")).toBeInTheDocument();
    expect(within(dialog).getByTestId("tutor-caret")).toBeInTheDocument();
    act(() => s.push(sse.delta("of **that**.") + sse.done()));
    act(() => s.close());
    expect(await within(dialog).findByText("that")).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).queryByTestId("tutor-caret")).not.toBeInTheDocument());
    expect(within(dialog).getByRole("button", { name: "Send" })).toBeInTheDocument();
    expect(input()).toHaveValue("");
  });

  it("Stop aborts the fetch and keeps the partial reply marked Stopped", async () => {
    const s = controlledSse();
    let signal: AbortSignal | null | undefined;
    route({
      "POST /api/tutor/threads": thread(),
      "POST /api/tutor/threads/5/messages": (init) => {
        signal = init.signal;
        return s.response();
      },
    });
    renderWithProviders(<Harness />);
    const { user, dialog } = await openDrawer();
    await user.type(input(), "Hi{Enter}");
    act(() => s.push(sse.start() + sse.delta("Partial answer")));
    expect(await within(dialog).findByText("Partial answer")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Stop" }));
    expect(await within(dialog).findByText("Stopped")).toBeInTheDocument();
    expect(signal?.aborted).toBe(true);
    expect(within(dialog).getByText("Partial answer")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Send" })).toBeInTheDocument();
  });

  it("shows an inline error with Retry that streams a new reply", async () => {
    let retries = 0;
    const fn = route({
      "POST /api/tutor/threads": thread(),
      "POST /api/tutor/threads/5/messages": () => sseResponse([sse.start(11), sse.error(11, "The local AI tutor isn't running.")]),
      "POST /api/tutor/messages/11/retry": () => {
        retries += 1;
        return sseResponse([sse.start(11), sse.delta("Second try works"), sse.done(11)]);
      },
    });
    renderWithProviders(<Harness />);
    const { user, dialog } = await openDrawer();
    await user.type(input(), "Hi{Enter}");
    expect(await within(dialog).findByText("The local AI tutor isn't running.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Retry" }));
    expect(await within(dialog).findByText("Second try works")).toBeInTheDocument();
    expect(retries).toBe(1);
    expect(within(dialog).queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(fn.mock.calls.some(([u]) => String(u) === "/api/tutor/messages/11/retry")).toBe(true);
  });

  it("resends the message when the failure happened before streaming", async () => {
    let attempt = 0;
    const fn = route({
      "POST /api/tutor/threads": thread(),
      "POST /api/tutor/threads/5/messages": () =>
        ++attempt === 1 ? jsonResponse({ detail: "Busy." }, 503) : sseResponse([sse.start(), sse.delta("OK now"), sse.done()]),
    });
    renderWithProviders(<Harness />);
    const { user, dialog } = await openDrawer();
    await user.type(input(), "Hi{Enter}");
    expect(await within(dialog).findByText("Busy.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Retry" }));
    expect(await within(dialog).findByText("OK now")).toBeInTheDocument();
    expect(within(dialog).getAllByText("Hi")).toHaveLength(1);
    expect(bodies(fn, "POST /api/tutor/threads/5/messages")).toHaveLength(2);
  });

  it("sends the new context with the next message and shows a divider", async () => {
    const fn = route({
      "POST /api/tutor/threads": thread(),
      "POST /api/tutor/threads/5/messages": () => sseResponse([sse.start(), sse.delta("ok"), sse.done()]),
    });
    renderWithProviders(<Harness />);
    const { user, dialog } = await openDrawer();
    await user.type(input(), "one{Enter}");
    await within(dialog).findByRole("button", { name: "Send" });
    act(() => setExercise(true));
    await user.type(input(), "two{Enter}");
    await waitFor(() => expect(bodies(fn, "POST /api/tutor/threads/5/messages")).toHaveLength(2));
    const [first, second] = bodies(fn, "POST /api/tutor/threads/5/messages");
    expect(first).toEqual({ content: "one" });
    expect(second).toEqual({
      content: "two",
      context: { lesson_id: "a2-imparfait", exercise_revision_id: 41, attempt_id: 7 },
    });
    expect(within(dialog).getByRole("separator")).toHaveTextContent("Now about: Exercise 4 · L'imparfait");
  });

  it("restores the thread from sessionStorage when opened", async () => {
    sessionStorage.setItem("frenchia.tutor.thread", "9");
    const fn = route({
      "GET /api/tutor/threads/9": () =>
        jsonResponse({
          id: 9,
          title: "x",
          context: { lesson_id: "a2-imparfait" },
          messages: [
            { id: 1, role: "user", content: "Earlier question", status: "complete", created_at: "" },
            { id: 2, role: "assistant", content: "Earlier answer", status: "complete", created_at: "" },
          ],
        }),
      "POST /api/tutor/threads/9/messages": () => sseResponse([sse.start(4), sse.delta("Next"), sse.done(4)]),
    });
    renderWithProviders(<Harness />);
    const { user, dialog } = await openDrawer();
    expect(await within(dialog).findByText("Earlier answer")).toBeInTheDocument();
    expect(within(dialog).getByText("Earlier question")).toBeInTheDocument();
    await user.type(input(), "More{Enter}");
    expect(await within(dialog).findByText("Next")).toBeInTheDocument();
    expect(fn.mock.calls.some(([u, i]) => String(u) === "/api/tutor/threads" && i?.method === "POST")).toBe(false);
    expect(bodies(fn, "POST /api/tutor/threads/9/messages")).toEqual([{ content: "More" }]);
  });

  it("New conversation clears the thread id and messages", async () => {
    const fn = route({
      "POST /api/tutor/threads": thread(),
      "POST /api/tutor/threads/5/messages": () => sseResponse([sse.start(), sse.delta("ok"), sse.done()]),
    });
    renderWithProviders(<Harness />);
    const { user, dialog } = await openDrawer();
    await user.type(input(), "one{Enter}");
    await within(dialog).findByText("ok");
    await user.click(within(dialog).getByRole("button", { name: "New conversation" }));
    expect(within(dialog).queryByText("ok")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("frenchia.tutor.thread")).toBeNull();
    await user.type(input(), "two{Enter}");
    await waitFor(() => expect(bodies(fn, "POST /api/tutor/threads")).toHaveLength(2));
  });

  it("Enter sends and Shift+Enter inserts a newline", async () => {
    const fn = route({
      "POST /api/tutor/threads": thread(),
      "POST /api/tutor/threads/5/messages": () => sseResponse([sse.start(), sse.delta("ok"), sse.done()]),
    });
    renderWithProviders(<Harness />);
    const { user } = await openDrawer();
    await user.type(input(), "line1{Shift>}{Enter}{/Shift}line2");
    expect(input()).toHaveValue("line1\nline2");
    expect(fn.mock.calls.some(([u]) => String(u).includes("/messages"))).toBe(false);
    await user.keyboard("{Enter}");
    await waitFor(() => expect(bodies(fn, "POST /api/tutor/threads/5/messages")).toEqual([{ content: "line1\nline2" }]));
  });

  it("disables sending while streaming (Enter does nothing)", async () => {
    const s = controlledSse();
    const fn = route({ "POST /api/tutor/threads": thread(), "POST /api/tutor/threads/5/messages": () => s.response() });
    renderWithProviders(<Harness />);
    const { user, dialog } = await openDrawer();
    await user.type(input(), "a{Enter}");
    await within(dialog).findByRole("button", { name: "Stop" });
    await user.type(input(), "b{Enter}");
    expect(bodies(fn, "POST /api/tutor/threads/5/messages")).toHaveLength(1);
    expect(within(dialog).queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
    act(() => s.close());
  });
});

describe("Ask the tutor from a result", () => {
  const exercise: PublicExercise = {
    exercise_revision_id: 41,
    id: "ex-04",
    type: "fill_blank",
    sentence: "Elle ___ à son ami.",
    hint: "(parler)",
  };

  async function answer(verdict: "incorrect" | "correct") {
    const fn = route({
      "POST /api/exercise-revisions/41/attempts": () => jsonResponse(attemptResult({ verdict, attempt_id: 7 }), 201),
      "POST /api/tutor/threads": thread(),
      "POST /api/tutor/threads/5/messages": () => sseResponse([sse.start(), sse.delta("Because."), sse.done()]),
    });
    renderWithProviders(
      <TutorDrawerProvider>
        <ExerciseCard exercise={exercise} number={4} lessonId="a2-imparfait" lessonTitle="L'imparfait" />
        <TutorDrawer />
      </TutorDrawerProvider>,
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Missing word"), "parlais");
    await user.click(screen.getByRole("button", { name: "Check" }));
    await user.click(await screen.findByRole("button", { name: "Ask the tutor about this" }));
    return { fn, user };
  }

  it("auto-sends 'Why is my answer wrong?' with the attempt context when incorrect", async () => {
    const { fn } = await answer("incorrect");
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Because.")).toBeInTheDocument();
    expect(bodies(fn, "POST /api/tutor/threads")).toEqual([
      { context: { lesson_id: "a2-imparfait", exercise_revision_id: 41, attempt_id: 7 } },
    ]);
    expect(bodies(fn, "POST /api/tutor/threads/5/messages")).toEqual([{ content: "Why is my answer wrong?" }]);
    expect(within(dialog).getByTestId("tutor-context")).toHaveTextContent("About: Exercise 4 · L'imparfait");
  });

  it("auto-sends 'Explain this point' when the answer was right", async () => {
    const { fn } = await answer("correct");
    await screen.findByRole("dialog");
    await waitFor(() => expect(bodies(fn, "POST /api/tutor/threads/5/messages")).toEqual([{ content: "Explain this point" }]));
  });
});
