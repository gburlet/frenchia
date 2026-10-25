import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { dashboardFixture } from "@/test/fixtures";
import { mockFetch, staffUser } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

function setup() {
  mockFetch({
    "GET /api/auth/me": { body: staffUser },
    "GET /api/health": { body: { status: "ok", services: {}, version: "1" } },
    "GET /api/curriculum": { body: { levels: [] } },
    "GET /api/dashboard": { body: dashboardFixture() },
    "GET /api/auth/csrf": { status: 204 },
    "POST /api/llm/warm": { status: 202, body: {} },
  });
  return renderApp("/");
}

describe("keyboard shortcuts", () => {
  afterEach(() => localStorage.clear());

  it("? lists the shortcuts and g + letter navigates", async () => {
    const user = userEvent.setup();
    const { router } = setup();
    await screen.findByText("Bonjour, marie");
    await user.keyboard("?");
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.keyboard("gp");
    await waitFor(() => expect(router.state.location.pathname).toBe("/progress"));
  });

  it("can be switched off", async () => {
    const user = userEvent.setup();
    const { router } = setup();
    await screen.findByText("Bonjour, marie");
    await user.click(screen.getByRole("button", { name: /Keyboard shortcuts/ }));
    await user.click(screen.getByRole("checkbox", { name: /Single-key shortcuts/ }));
    await user.keyboard("{Escape}");
    await user.keyboard("gp");
    expect(router.state.location.pathname).toBe("/");
  });

  it("ignores keys typed into a text box", async () => {
    const user = userEvent.setup();
    const { router } = setup();
    await user.click(await screen.findByRole("button", { name: /Keyboard shortcuts/ }));
    await user.keyboard("{Escape}");
    const input = document.createElement("input");
    document.body.append(input);
    input.focus();
    await user.keyboard("gp?");
    expect(router.state.location.pathname).toBe("/");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    input.remove();
  });
});
