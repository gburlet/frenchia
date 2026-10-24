import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { lessonFixture } from "@/test/fixtures";
import { mockFetch, staffUser } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

const csrf = {
  "GET /api/auth/csrf": () => {
    document.cookie = "csrftoken=tok; path=/";
    return { status: 204 };
  },
};

describe("Lesson reader", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=tok; path=/";
  });

  it("renders every section type", async () => {
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/lessons/a2-passe-compose-er": { body: lessonFixture },
      "GET /api/curriculum": { body: { levels: [] } },
      ...csrf,
    });
    const user = userEvent.setup();
    renderApp("/lessons/a2-passe-compose-er");
    expect(await screen.findByRole("heading", { level: 1, name: lessonFixture.title })).toBeInTheDocument();
    expect(screen.getByText("The passé composé of -er verbs")).toBeInTheDocument();
    expect(screen.getByText(/33 min/)).toBeInTheDocument();
    expect(screen.getByText("Form the passé composé")).toBeInTheDocument();

    // explanation (markdown, raw html not rendered)
    expect(screen.getByText("avoir").tagName).toBe("STRONG");
    expect(screen.getByText("participe passé").tagName).toBe("EM");
    expect(screen.getAllByRole("listitem").some((li) => li.textContent === "item one")).toBe(true);
    expect(document.querySelector("b")).toBeNull();

    // examples
    expect(screen.getByText("J’ai mangé une poutine.")).toBeInTheDocument();
    expect(screen.getAllByText("QC")).toHaveLength(2); // example + vocab
    expect(screen.getByText("Très québécois")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Écouter : Elle a parlé." })).toBeInTheDocument();

    // table
    const table = screen.getByRole("table", { name: "Parler au passé composé" });
    expect(within(table).getByRole("columnheader", { name: "Forme" })).toBeInTheDocument();
    expect(within(table).getByText("j’ai parlé")).toBeInTheDocument();

    // vocabulary
    expect(screen.getByText("un livre")).toBeInTheDocument();
    expect(screen.getByText("l’école")).toBeInTheDocument();
    expect(screen.getByText("familiar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Écouter : un livre" })).toBeInTheDocument();

    // reading
    expect(screen.getByRole("heading", { name: "Ma fin de semaine" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play all" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Écouter la phrase 2" })).toBeInTheDocument();
    expect(screen.queryByText("On Saturday I walked. Then I ate!")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show translation" }));
    expect(screen.getByText("On Saturday I walked. Then I ate!")).toBeInTheDocument();
    expect(screen.getByText("to walk")).toBeInTheDocument();

    // regional note
    expect(screen.getByRole("heading", { name: "Au Québec" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Regional variants" })).toBeInTheDocument();
    expect(screen.getByText("une voiture")).toBeInTheDocument();

    // practice
    expect(screen.getByRole("heading", { name: "Practice" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /1\.\s*Fill in the blank/ })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /2\.\s*Translate/ })).toBeInTheDocument();

    // footer nav
    expect(screen.getByRole("link", { name: /Leçon précédente/ })).toHaveAttribute("href", "/lessons/a2-prev");
    expect(screen.getByRole("link", { name: /Leçon suivante/ })).toHaveAttribute("href", "/lessons/a2-next");
  });

  it("marks a not-started lesson in progress on mount", async () => {
    const fetchMock = mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/lessons/a2-passe-compose-er": {
        body: { ...lessonFixture, progress: { status: "not_started", completed_at: null } },
      },
      "POST /api/lessons/a2-passe-compose-er/progress": {
        body: { status: "in_progress", completed_at: null },
      },
      "GET /api/curriculum": { body: { levels: [] } },
    });
    renderApp("/lessons/a2-passe-compose-er");
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/progress"));
      expect(call).toBeDefined();
      expect(JSON.parse(call![1]!.body as string)).toEqual({});
    });
  });

  it("posts completed: true and shows the completed state", async () => {
    const fetchMock = mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/lessons/a2-passe-compose-er": { body: lessonFixture },
      "POST /api/lessons/a2-passe-compose-er/progress": {
        body: { status: "completed", completed_at: "2026-10-24T00:00:00Z" },
      },
      "GET /api/curriculum": { body: { levels: [] } },
    });
    const user = userEvent.setup();
    renderApp("/lessons/a2-passe-compose-er");
    await user.click(await screen.findByRole("button", { name: "Marquer comme terminée" }));
    expect(await screen.findByText("Leçon terminée")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/progress"))!;
    expect(JSON.parse(call[1]!.body as string)).toEqual({ completed: true });
    expect(screen.queryByRole("button", { name: "Marquer comme terminée" })).not.toBeInTheDocument();
  });

  it("shows the 404 state", async () => {
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/lessons/nope": { status: 404, body: { detail: "Not found." } },
    });
    renderApp("/lessons/nope");
    expect(await screen.findByText("This lesson isn’t published yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the curriculum" })).toHaveAttribute("href", "/curriculum");
  });

  it("shows an error state on server failure", async () => {
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/lessons/boom": { status: 500, body: { detail: "Kaput" } },
    });
    renderApp("/lessons/boom");
    expect(await screen.findByRole("alert")).toHaveTextContent("Kaput");
  });
});

