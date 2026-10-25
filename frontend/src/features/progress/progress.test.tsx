import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { attemptResult, curriculumFixture, dashboardFixture } from "@/test/fixtures";
import { mockFetch, staffUser } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";
import type { ReviewItem, ReviewSet } from "@/lib/api/progress";

const weak = dashboardFixture().weak_topics;

const item = (id: number, over: Partial<ReviewItem> = {}): ReviewItem => ({
  exercise: {
    exercise_revision_id: id,
    id: `ex-0${id}`,
    type: "fill_blank",
    sentence: `Hier, elle ___ au dépanneur ${id}.`,
    hint: "(aller)",
    translation_en: "Yesterday she went to the store.",
  },
  topic: { id: "passe-compose-etre", title: "Passé composé with être" },
  source: "missed",
  source_label: "answered wrong last time",
  ai_generated: false,
  lesson: { id: "a2-passe-compose-etre", title: "Le passé composé avec être" },
  result: null,
  ...over,
});

const reviewSet = (over: Partial<ReviewSet> = {}): ReviewSet => ({
  id: 3,
  created_at: "2026-10-25T10:00:00Z",
  completed_at: null,
  topics: weak,
  extras: "ready",
  items: [item(1), item(2, { source: "generated", source_label: "AI-generated for you", ai_generated: true })],
  ...over,
});

describe("Dashboard", () => {
  it("shows today's numbers, weak topics and the activity chart", async () => {
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/curriculum": { body: curriculumFixture },
      "GET /api/health": { body: { status: "ok", services: {}, version: "1" } },
      "GET /api/dashboard": { body: dashboardFixture() },
    });
    renderApp("/");
    const tiles = await screen.findByRole("region", { name: "Today at a glance" });
    expect(within(tiles).getByText("3")).toBeInTheDocument();
    expect(within(tiles).getByText("75%")).toBeInTheDocument();
    expect(within(tiles).getByRole("link", { name: /vocabulary cards to review\s*15/ })).toHaveAttribute(
      "href",
      "/practice/vocab/review",
    );
    expect(screen.getByText(/42% recent accuracy over 6 tries/)).toBeInTheDocument();
    const today = screen.getByLabelText(/Sun, Oct 25: 12 items, 9 min \(8 exercises, 4 vocab\)/);
    await userEvent.setup().hover(today);
    expect(screen.getByRole("tooltip")).toHaveTextContent("12 items");
  });

  it("starts a review and opens it", async () => {
    let current: ReviewSet | null = null;
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/curriculum": { body: curriculumFixture },
      "GET /api/health": { body: { status: "ok", services: {}, version: "1" } },
      "GET /api/dashboard": { body: dashboardFixture() },
      "GET /api/auth/csrf": { status: 204 },
      "POST /api/review": () => {
        current = reviewSet({ extras: "queued" });
        return { status: 201, body: current };
      },
      "GET /api/review": () => ({ body: { current, weak_topics: weak } }),
    });
    const user = userEvent.setup();
    const { router } = renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Start a review" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/practice/review"));
    expect(await screen.findByText("Hier, elle")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("writing new exercises");
  });
});

describe("Review", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=tok; path=/";
  });

  it("walks through the items, labels AI-generated ones and finishes", async () => {
    let completed = false;
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/review": () => ({ body: { current: completed ? null : reviewSet(), weak_topics: weak } }),
      "POST /api/exercise-revisions/1/attempts": { status: 201, body: attemptResult({ verdict: "incorrect", score: 0 }) },
      "POST /api/exercise-revisions/2/attempts": { status: 201, body: attemptResult() },
      "POST /api/review/3/complete": () => {
        completed = true;
        return { body: { ...reviewSet(), completed_at: "2026-10-25T10:10:00Z" } };
      },
      "GET /api/dashboard": { body: dashboardFixture() },
      "GET /api/curriculum": { body: curriculumFixture },
      "GET /api/health": { body: { status: "ok", services: {}, version: "1" } },
    });
    const user = userEvent.setup();
    const { router } = renderApp("/practice/review");
    expect(await screen.findByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("answered wrong last time")).toBeInTheDocument();
    expect(screen.queryByText("AI-generated")).not.toBeInTheDocument();

    await user.type(screen.getByRole("textbox"), "a allé{Enter}");
    const next = await screen.findByRole("button", { name: /Next/ });
    await waitFor(() => expect(next).toHaveFocus());
    await user.keyboard("{Enter}");

    expect(await screen.findByText("2 / 2")).toBeInTheDocument();
    expect(screen.getByText("AI-generated")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "est allée{Enter}");
    await user.click(await screen.findByRole("button", { name: /See results/ }));
    expect(await screen.findByText(/1 of 2 right/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finish" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });

  it("explains why a review can't start yet", async () => {
    mockFetch({
      "GET /api/auth/me": { body: staffUser },
      "GET /api/review": { body: { current: null, weak_topics: [] } },
      "POST /api/review": { status: 404, body: { detail: "Nothing to review yet: practise a lesson's exercises first, then come back." } },
    });
    const user = userEvent.setup();
    renderApp("/practice/review");
    await user.click(await screen.findByRole("button", { name: "Start a review" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing to review yet");
  });
});

describe("Progress page", () => {
  it("shows topic and tense accuracy as meters", async () => {
    mockFetch({ "GET /api/auth/me": { body: staffUser }, "GET /api/dashboard": { body: dashboardFixture() } });
    renderApp("/progress");
    const meter = await screen.findByRole("meter", { name: "Passé composé with être: recent accuracy" });
    expect(meter).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByRole("meter", { name: "Passé composé: recent accuracy" })).toHaveAttribute("aria-valuenow", "60");
    expect(screen.getByText("2 of 6")).toBeInTheDocument();
    expect(screen.getByText("auxiliary · 3")).toBeInTheDocument();
  });
});
