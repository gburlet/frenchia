import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { curriculumFixture, dashboardFixture } from "@/test/fixtures";
import { mockFetch, staffUser } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

function setup(curriculum = curriculumFixture) {
  return mockFetch({
    "GET /api/auth/me": { body: staffUser },
    "GET /api/curriculum": { body: curriculum },
  });
}

describe("Curriculum browser", () => {
  it("renders level tabs, defaults to the in-progress level and shows units", async () => {
    setup();
    renderApp("/curriculum");
    const tabs = await screen.findAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["A1", "A2", "B1", "B2"]);
    expect(screen.getByRole("tab", { name: "A2" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "A2 · Élémentaire" })).toBeInTheDocument();
    expect(screen.getByText("Everyday situations.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Raconter au passé" })).toBeInTheDocument();
    expect(screen.getByText("Tell what happened")).toBeInTheDocument();
  });

  it("shows status pills; unpublished lessons are not links", async () => {
    setup();
    renderApp("/curriculum");
    const link = await screen.findByRole("link", { name: /Le passé composé des verbes en -er/ });
    expect(link).toHaveAttribute("href", "/lessons/a2-passe-compose-er");
    expect(within(link).getByText("In progress")).toBeInTheDocument();
    const done = screen.getByRole("link", { name: /avec être/ });
    expect(within(done).getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Bientôt")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /imparfait/ })).not.toBeInTheDocument();
    expect(screen.getByText("L’imparfait")).toBeInTheDocument();
  });

  it("switches level with the keyboard", async () => {
    setup();
    renderApp("/curriculum");
    const user = userEvent.setup();
    const a2 = await screen.findByRole("tab", { name: "A2" });
    a2.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "B1" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "B1 · Intermédiaire" })).toBeInTheDocument();
  });

  it("opens the level named in the URL and keeps it there", async () => {
    setup();
    renderApp("/curriculum?level=b1");
    expect(await screen.findByRole("tab", { name: "B1" })).toHaveAttribute("aria-selected", "true");
    await userEvent.setup().click(screen.getByRole("tab", { name: "A1" }));
    expect(screen.getByRole("tab", { name: "A1" })).toHaveAttribute("aria-selected", "true");
  });

  it("ignores an unknown level in the URL", async () => {
    setup();
    renderApp("/curriculum?level=C2");
    expect(await screen.findByRole("tab", { name: "A2" })).toHaveAttribute("aria-selected", "true");
  });

  it("defaults to the level of the furthest completed lesson", async () => {
    const copy = structuredClone(curriculumFixture);
    const done = structuredClone(copy.levels[1]!.units[0]!.lessons[1]!);
    copy.levels[2]!.units = [{ id: "b1-u01", title: "Donner son avis", objectives: [], lessons: [done] }];
    setup(copy);
    renderApp("/curriculum");
    expect(await screen.findByRole("tab", { name: "B1" })).toHaveAttribute("aria-selected", "true");
  });

  it("the header Curriculum link returns to the learner's level", async () => {
    setup();
    renderApp("/curriculum?level=B2");
    const user = userEvent.setup();
    expect(await screen.findByRole("tab", { name: "B2" })).toHaveAttribute("aria-selected", "true");
    await user.click(within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: "Curriculum" }));
    expect(screen.getByRole("tab", { name: "A2" })).toHaveAttribute("aria-selected", "true");
  });

  it("defaults to A2 when nothing is in progress", async () => {
    const copy = structuredClone(curriculumFixture);
    copy.levels[1]!.units[0]!.lessons[0]!.progress.status = "not_started";
    setup(copy);
    renderApp("/curriculum");
    expect(await screen.findByRole("tab", { name: "A2" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows a Continue card on the dashboard", async () => {
    setup();
    mockFetchForDashboard();
    renderApp("/");
    const link = await screen.findByRole("link", { name: /Le passé composé des verbes en -er/ });
    expect(link).toHaveAttribute("href", "/lessons/a2-passe-compose-er");
  });
});

function mockFetchForDashboard() {
  mockFetch({
    "GET /api/auth/me": { body: staffUser },
    "GET /api/curriculum": { body: curriculumFixture },
    "GET /api/health": { body: { status: "ok", services: {}, version: "1" } },
    "GET /api/dashboard": { body: dashboardFixture() },
  });
}
