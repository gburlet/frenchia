import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { attemptResult } from "@/test/fixtures";
import { mockFetch, staffUser } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

const options = {
  levels: ["A1", "A2"],
  topics: [
    { id: "passe-compose-avoir", title: "Passé composé with avoir", level: "A2", count: 4 },
    { id: "articles", title: "Articles", level: "A1", count: 2 },
  ],
};
const exercise = (rev: number, prompt: string) => ({
  exercise_revision_id: rev,
  id: `ex-${rev}`,
  type: "translate",
  direction: "en_fr",
  prompt,
  hint: null,
  lesson: { id: "a2-passe-compose-er", title: "Le passé composé", level: "A2" },
});

describe("Translation Station", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=tok; path=/";
  });

  it("builds the query string from URL filters and from changes", async () => {
    const fetchMock = mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/practice/translate/options": { body: options },
      "GET /api/practice/translate/next?level=A2&topic=passe-compose-avoir": { body: exercise(1, "First prompt.") },
      "GET /api/practice/translate/next?level=A2&topic=passe-compose-avoir&direction=fr_en": {
        body: exercise(2, "Second prompt."),
      },
    });
    const user = userEvent.setup();
    const { router } = renderApp("/practice/translate?level=A2&topic=passe-compose-avoir");
    expect(await screen.findByText("First prompt.")).toBeInTheDocument();
    expect(screen.getByLabelText("Level")).toHaveValue("A2");
    // topics are filtered by level, with counts
    expect(await screen.findByRole("option", { name: "Passé composé with avoir (4)" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Articles/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Le passé composé" })).toHaveAttribute(
      "href",
      "/lessons/a2-passe-compose-er",
    );
    await user.selectOptions(screen.getByLabelText("Direction"), "fr_en");
    expect(await screen.findByText("Second prompt.")).toBeInTheDocument();
    expect(router.state.location.search).toBe("?level=A2&topic=passe-compose-avoir&direction=fr_en");
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toContain(
      "/api/practice/translate/next?level=A2&topic=passe-compose-avoir&direction=fr_en",
    );
  });

  it("changing level clears the topic", async () => {
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/practice/translate/options": { body: options },
      "GET /api/practice/translate/next?level=A2&topic=passe-compose-avoir": { body: exercise(1, "First prompt.") },
      "GET /api/practice/translate/next?level=A1": { body: exercise(3, "A1 prompt.") },
    });
    const user = userEvent.setup();
    const { router } = renderApp("/practice/translate?level=A2&topic=passe-compose-avoir");
    await screen.findByText("First prompt.");
    await user.selectOptions(screen.getByLabelText("Level"), "A1");
    expect(await screen.findByText("A1 prompt.")).toBeInTheDocument();
    expect(router.state.location.search).toBe("?level=A1");
  });

  it("offers Next after a result (button and n key)", async () => {
    let n = 0;
    const fetchMock = mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/practice/translate/options": { body: options },
      "GET /api/practice/translate/next": () => ({ body: exercise(++n, `Prompt ${n}.`) }),
      "POST /api/exercise-revisions/1/attempts": { body: attemptResult() },
      "POST /api/exercise-revisions/2/attempts": { body: attemptResult() },
    });
    const user = userEvent.setup();
    renderApp("/practice/translate");
    await screen.findByText("Prompt 1.");
    expect(screen.queryByRole("button", { name: /Next/ })).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Your translation" }), "réponse{Enter}");
    await user.click(await screen.findByRole("button", { name: /Next/ }));
    expect(await screen.findByText("Prompt 2.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Your translation" }), "réponse{Enter}");
    await screen.findByRole("button", { name: /Next/ });
    await user.keyboard("n");
    expect(await screen.findByText("Prompt 3.")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([u]) => String(u).includes("/next")).length).toBe(3),
    );
  });

  it("shows the empty state on 404", async () => {
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/practice/translate/options": { body: options },
      "GET /api/practice/translate/next?level=A1": { status: 404, body: { detail: "none" } },
    });
    renderApp("/practice/translate?level=A1");
    expect(await screen.findByText("No translation exercises match yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse the curriculum" })).toHaveAttribute("href", "/curriculum");
  });
});
