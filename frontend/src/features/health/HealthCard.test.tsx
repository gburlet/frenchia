import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockFetch } from "@/test/mockFetch";
import { HealthCard } from "./HealthCard";

function renderCard() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <HealthCard />
    </QueryClientProvider>,
  );
}

describe("HealthCard", () => {
  it("renders a pill per service", async () => {
    mockFetch({
      "GET /api/health": {
        body: { status: "ok", services: { database: "ok", llm: "error" }, version: "0.1" },
      },
    });
    renderCard();
    expect(await screen.findByText("Database")).toBeInTheDocument();
    expect(screen.getByText("Language model")).toBeInTheDocument();
    expect(screen.getByText("error")).toHaveClass("bg-failure");
    expect(screen.getAllByText("ok").every((el) => el.classList.contains("bg-success"))).toBe(true);
  });

  it("renders the degraded body on 503", async () => {
    mockFetch({
      "GET /api/health": {
        status: 503,
        body: { status: "degraded", services: { database: "error" }, version: "0.1" },
      },
    });
    renderCard();
    expect(await screen.findByText("degraded")).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    mockFetch({ "GET /api/health": { status: 500, body: {} } });
    renderCard();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load system status");
  });
});
