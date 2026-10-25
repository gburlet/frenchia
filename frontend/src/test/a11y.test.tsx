// Automated accessibility audit (axe-core) of the main pages, rendered with mocked API data.
// jsdom has no layout, so colour contrast is checked against the style guide instead (see
// docs/accessibility.md); everything else axe can see in the DOM is enforced here.
import { screen } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";
import type { ReviewSet } from "@/lib/api/progress";
import { curriculumFixture, dashboardFixture, lessonFixture } from "./fixtures";
import { mockFetch, staffUser } from "./mockFetch";
import { renderApp } from "./renderApp";

const health = { status: "ok", services: { database: "ok", llm: "ok", tts: "ok" }, version: "1" };
const vocabStats = dashboardFixture().vocab;
const review: ReviewSet = {
  id: 3,
  created_at: "2026-10-25T10:00:00Z",
  completed_at: null,
  topics: dashboardFixture().weak_topics,
  extras: "running",
  items: [
    {
      exercise: { exercise_revision_id: 1, id: "p-01", type: "multiple_choice", question: "Which is right?", options: ["Je suis allé", "J’ai allé"] },
      topic: { id: "passe-compose-etre", title: "Passé composé with être" },
      source: "generated",
      source_label: "AI-generated for you",
      ai_generated: true,
      lesson: { id: "a2-passe-compose-etre", title: "Le passé composé avec être" },
      result: null,
    },
  ],
};

const api = {
  "GET /api/auth/me": { body: staffUser },
  "GET /api/health": { body: health },
  "GET /api/curriculum": { body: curriculumFixture },
  "GET /api/dashboard": { body: dashboardFixture() },
  "GET /api/lessons/a2-passe-compose-er": { body: lessonFixture },
  "GET /api/review": { body: { current: review, weak_topics: review.topics } },
  "GET /api/practice/translate/options": {
    body: { levels: ["A2"], topics: [{ id: "passe-compose-avoir", title: "Passé composé with avoir", level: "A2", count: 4 }] },
  },
  "GET /api/practice/translate/next": {
    body: {
      exercise_revision_id: 9, id: "ex-09", type: "translate", direction: "en_fr", prompt: "We went shopping.", hint: null,
      lesson: { id: "a2-passe-compose-er", title: "Le passé composé", level: "A2" },
    },
  },
  "GET /api/vocab/sets": {
    body: {
      sets: [{ slug: "a1-hiver", kind: "theme", level: "A1", title: "L'hiver", title_en: "Winter", lesson: null, size: 20, in_deck: 5, seen: 3, due: 1 }],
      stats: vocabStats,
    },
  },
};

async function audit(): Promise<axe.Result[]> {
  const results = await axe.run(document.body, {
    rules: { "color-contrast": { enabled: false } },
    resultTypes: ["violations"],
  });
  return results.violations;
}

function summary(violations: axe.Result[]): string[] {
  return violations.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`);
}

describe("accessibility (axe)", () => {
  it.each([
    ["/", "Bonjour, marie"],
    ["/curriculum", "Curriculum"],
    ["/lessons/a2-passe-compose-er", lessonFixture.title],
    ["/practice/translate", "We went shopping."],
    ["/practice/vocab", "L'hiver"],
    ["/practice/review", "Which is right?"],
    ["/progress", "Grammar topics"],
  ])("%s has no violations", async (path, text) => {
    mockFetch(api);
    renderApp(path);
    expect((await screen.findAllByText(text)).length).toBeGreaterThan(0);
    expect(summary(await audit())).toEqual([]);
  });

  it("the login page has no violations", async () => {
    mockFetch({ "GET /api/auth/me": { status: 403, body: { detail: "Not logged in" } } });
    renderApp("/login");
    await screen.findByRole("button", { name: "Sign in" });
    expect(summary(await audit())).toEqual([]);
  });
});
