import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { mockFetch, staffUser } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";
import { formatInterval } from "./format";

const stats = {
  cards: 44, words: 22, due_now: 4, due_today: 9, new_waiting: 20,
  new_remaining_today: 11, new_today: 11, reviews_today: 16, mature: 0,
};
const setsBody = {
  sets: [
    { slug: "a1-hiver", kind: "theme", level: "A1", title: "La météo et l'hiver", title_en: "Weather and winter", lesson: null, size: 22, in_deck: 11, seen: 10, due: 4 },
    { slug: "a2-vetements", kind: "theme", level: "A2", title: "Les vêtements", title_en: "Clothes", lesson: null, size: 10, in_deck: 0, seen: 0, due: 0 },
    { slug: "lesson-a2-imparfait", kind: "lesson", level: "A2", title: "L'imparfait", title_en: "Imperfect", lesson: "a2-imparfait", size: 5, in_deck: 0, seen: 0, due: 0 },
  ],
  stats,
};
const lexeme = (over: Record<string, unknown> = {}) => ({
  id: 12, fr: "tuque", display: "la tuque", article: "la", en: "winter hat", pos: "noun",
  gender: "f", plural: null, region: "qc", formality: "standard",
  example_fr: "Je mets ma tuque.", example_en: "I put on my hat.", note: "France: un bonnet", set: "a1-hiver", ...over,
});
const previews = { "1": 60, "2": 360, "3": 600, "4": 1036800 };
const card = (over: Record<string, unknown> = {}) => ({
  id: 7, direction: "recognize", is_new: true, due: "2026-10-25T02:08:26Z", lexeme: lexeme(), previews, ...over,
});
const batch = (cards: unknown[], over: Record<string, unknown> = {}) => ({
  cards, due_count: 4, new_remaining_today: 11, next_due: null, ...over,
});

describe("formatInterval", () => {
  it.each([
    [30, "<1 min"],
    [600, "10 min"],
    [3 * 3600, "3 h"],
    [4 * 86400, "4 d"],
    [1036800, "12 d"],
    [60 * 86400, "2 mo"],
    [Math.round(1.3 * 365 * 86400), "1.3 y"],
  ])("%s s -> %s", (s, text) => expect(formatInterval(s)).toBe(text));
});

describe("Vocabulary Station", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=tok; path=/";
  });

  it("renders stats, level groups and lesson sets", async () => {
    mockFetch({ "GET /api/auth/me": { body: staffUser }, "GET /api/vocab/sets": { body: setsBody } });
    renderApp("/practice/vocab");
    expect(await screen.findByText("La météo et l'hiver")).toBeInTheDocument();
    expect(screen.getByText("Due now")).toBeInTheDocument();
    expect(screen.getByText("Words in deck")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review now" })).toHaveAttribute("href", "/practice/vocab/review");
    expect(screen.getByText("15")).toBeInTheDocument(); // 4 due + 11 new
    const a1 = screen.getByRole("region", { name: "Level A1" });
    expect(within(a1).getByRole("link", { name: /La météo/ })).toHaveAttribute("href", "/practice/vocab/sets/a1-hiver");
    expect(within(a1).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "11");
    expect(screen.getByRole("region", { name: "Level A2" })).toHaveTextContent("Les vêtements");
    expect(within(screen.getByRole("region", { name: "From your lessons" })).getByText("L'imparfait")).toBeInTheDocument();
  });

  it("does not count the daily new-card allowance as waiting when the deck is empty", async () => {
    const empty = { ...stats, cards: 0, words: 0, due_now: 0, new_waiting: 0, new_remaining_today: 15, new_today: 0, reviews_today: 0 };
    mockFetch({ "GET /api/auth/me": { body: staffUser }, "GET /api/vocab/sets": { body: { ...setsBody, stats: empty } } });
    renderApp("/practice/vocab");
    expect(await screen.findByText("Your deck is empty")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review now" })).not.toBeInTheDocument();
  });

  it("adds a set to the reviews", async () => {
    let learned = false;
    const word = (status: string) => ({ ...lexeme(), status });
    const fetchMock = mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/vocab/sets": { body: setsBody },
      "GET /api/vocab/sets/a1-hiver": () => ({
        body: { slug: "a1-hiver", kind: "theme", level: "A1", title: "La météo et l'hiver", title_en: "Weather and winter", lesson: null, words: [word(learned ? "new" : "not_started")] },
      }),
      "POST /api/vocab/sets/a1-hiver/learn": () => {
        learned = true;
        return { body: { added: 1, skipped: 2 } };
      },
    });
    const user = userEvent.setup();
    renderApp("/practice/vocab/sets/a1-hiver");
    expect(await screen.findByText("la tuque")).toBeInTheDocument();
    expect(screen.getByTitle("Québec usage")).toHaveTextContent("QC");
    expect(screen.getByText("Not in deck")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review now" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add these words to my reviews" }));
    expect(await screen.findByText("Added 1 word (2 already in your deck)")).toBeInTheDocument();
    expect(await screen.findByText("In your reviews")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review now" })).toHaveAttribute("href", "/practice/vocab/review");
    expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith("/learn") && i?.method === "POST")).toBe(true);
  });

  it("adds and removes a single word from the set page", async () => {
    let inDeck = false;
    const posts: string[] = [];
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/vocab/sets/a1-hiver": () => ({
        body: {
          slug: "a1-hiver", kind: "theme", level: "A1", title: "La météo et l'hiver", title_en: "Weather and winter", lesson: null,
          words: [
            { ...lexeme(), status: inDeck ? "new" : "not_started" },
            { ...lexeme({ id: 13, fr: "manteau", display: "le manteau", en: "coat", gender: "m" }), status: "elsewhere" },
          ],
        },
      }),
      "POST /api/vocab/words/12/add": () => {
        posts.push("add");
        inDeck = true;
        return { body: { lexeme: 12, added: true } };
      },
      "POST /api/vocab/words/12/remove": () => {
        posts.push("remove");
        inDeck = false;
        return { body: { lexeme: 12, removed: true } };
      },
    });
    const user = userEvent.setup();
    renderApp("/practice/vocab/sets/a1-hiver");
    expect(await screen.findByText("In deck via another set")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /deck: le manteau/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add to deck: la tuque" }));
    await user.click(await screen.findByRole("button", { name: "Remove from deck: la tuque" }));
    expect(await screen.findByRole("button", { name: "Add to deck: la tuque" })).toBeInTheDocument();
    expect(posts).toEqual(["add", "remove"]);
  });

  it("removes a set from the reviews", async () => {
    let removed = false;
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/vocab/sets/a1-hiver": () => ({
        body: { slug: "a1-hiver", kind: "theme", level: "A1", title: "La météo et l'hiver", title_en: "Weather and winter", lesson: null, words: [{ ...lexeme(), status: removed ? "not_started" : "learning" }] },
      }),
      "POST /api/vocab/sets/a1-hiver/remove": () => {
        removed = true;
        return { body: { removed: 1 } };
      },
    });
    const user = userEvent.setup();
    renderApp("/practice/vocab/sets/a1-hiver");
    await user.click(await screen.findByRole("button", { name: "Remove from my reviews" }));
    expect(await screen.findByText(/Removed 1 word from your reviews/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Add these words to my reviews" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review now" })).not.toBeInTheDocument();
  });

  it("reveals a recognize card then rates it with the keyboard", async () => {
    let posted: Record<string, unknown> | null = null;
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/vocab/review?limit=20": { body: batch([card(), card({ id: 8, lexeme: lexeme({ id: 13, display: "le froid", en: "cold" }) })]) },
      "POST /api/vocab/cards/7/review": (init) => {
        posted = JSON.parse(String(init?.body));
        return { body: { id: 7, due: "x", interval_seconds: 600 } };
      },
    });
    const user = userEvent.setup();
    renderApp("/practice/vocab/review");
    expect(await screen.findByText("la tuque")).toBeInTheDocument();
    expect(screen.queryByText("winter hat")).not.toBeInTheDocument();
    await user.keyboard(" ");
    expect(await screen.findByText("winter hat")).toBeInTheDocument();
    expect(screen.getByText("10 min")).toBeInTheDocument();
    expect(screen.getByText("12 d")).toBeInTheDocument();
    await user.keyboard("3");
    expect(await screen.findByText("le froid")).toBeInTheDocument();
    expect(posted).toMatchObject({ rating: 3 });
    expect(typeof (posted as unknown as { duration_ms: number }).duration_ms).toBe("number");
    expect(posted).not.toHaveProperty("answer");
  });

  it("removes a word, skips its other direction in the batch, and undoes", async () => {
    const posts: unknown[] = [];
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/vocab/review?limit=20": {
        body: batch([
          card(),
          card({ id: 9, direction: "recall" }), // same word, other direction
          card({ id: 8, lexeme: lexeme({ id: 13, display: "le froid", en: "cold" }) }),
        ]),
      },
      "POST /api/vocab/cards/7/remove": (init) => {
        posts.push(JSON.parse(String(init?.body)));
        return { body: { lexeme: 12, removed: true } };
      },
    });
    const user = userEvent.setup();
    renderApp("/practice/vocab/review");
    expect(await screen.findByText("la tuque")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove this word" }));
    expect(await screen.findByText("le froid")).toBeInTheDocument();
    expect(screen.getByText(/1 left in this batch/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Removed la tuque from your reviews.");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument());
    expect(posts).toEqual([{ removed: true }, { removed: false }]);
  });

  it("checks a recall card, pre-selects the suggested rating and posts the answer", async () => {
    let posted: Record<string, unknown> | null = null;
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/vocab/review?limit=20": { body: batch([card({ direction: "recall", is_new: false })]) },
      "POST /api/vocab/cards/7/check": { body: { result: "gender", correct: false, expected: "la tuque", message: "tuque is feminine: la tuque.", suggested_rating: 2 } },
      "POST /api/vocab/cards/7/review": (init) => {
        posted = JSON.parse(String(init?.body));
        return { body: { id: 7, due: "x", interval_seconds: 360 } };
      },
      "GET /api/vocab/review?limit=20&ahead=1": { body: batch([]) },
    });
    const user = userEvent.setup();
    renderApp("/practice/vocab/review");
    const input = await screen.findByLabelText("Your French answer");
    expect(screen.queryByText("la tuque")).not.toBeInTheDocument();
    await user.type(input, "le tuque{Enter}");
    expect(await screen.findByText("tuque is feminine: la tuque.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Hard/ })).toHaveAttribute("aria-pressed", "true");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(posted).toEqual(expect.objectContaining({ rating: 2, answer: "le tuque", check_result: "gender" })));
  });

  it("shows All caught up and offers learn ahead", async () => {
    const soon = new Date(Date.now() + 5 * 60_000).toISOString();
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/vocab/review?limit=20": { body: batch([], { next_due: soon, new_remaining_today: 0 }) },
      "GET /api/vocab/review?limit=20&ahead=1": { body: batch([card()]) },
      "GET /api/vocab/sets": { body: setsBody },
    });
    const user = userEvent.setup();
    renderApp("/practice/vocab/review");
    expect(await screen.findByText("All caught up")).toBeInTheDocument();
    expect(await screen.findByText(/daily limit|limit of new cards/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Learn ahead" }));
    expect(await screen.findByText("la tuque")).toBeInTheDocument();
  });
});
