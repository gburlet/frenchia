import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { dashboardFixture } from "@/test/fixtures";
import { mockFetch, staffUser } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

const health = { status: "ok", services: { database: "ok" }, version: "1" };

describe("RequireAuth", () => {
  it("redirects to /login on 403", async () => {
    mockFetch({ "GET /api/auth/me": { status: 403, body: { detail: "Forbidden" } } });
    const { router } = renderApp("/curriculum");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });
});

describe("LoginPage", () => {
  it("submits and redirects to the original location", async () => {
    let loggedIn = false;
    const fetchMock = mockFetch({
      "GET /api/curriculum": { body: { levels: [] } },
      "GET /api/auth/me": () =>
        loggedIn ? { body: staffUser } : { status: 403, body: { detail: "Forbidden" } },
      "GET /api/auth/csrf": () => {
        document.cookie = "csrftoken=tok; path=/";
        return { status: 204 };
      },
      "POST /api/auth/login": () => {
        loggedIn = true;
        return { body: staffUser };
      },
    });
    const user = userEvent.setup();
    const { router } = renderApp("/curriculum");
    await user.type(await screen.findByLabelText("Username"), "marie");
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Curriculum" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/curriculum");
    const loginCall = fetchMock.mock.calls.find(([url]) => url === "/api/auth/login")!;
    expect(JSON.parse(loginCall[1]!.body as string)).toEqual({ username: "marie", password: "secret" });
  });

  it("shows the error on 400", async () => {
    mockFetch({
      "GET /api/auth/me": { status: 403, body: {} },
      "GET /api/auth/csrf": () => {
        document.cookie = "csrftoken=tok; path=/";
        return { status: 204 };
      },
      "POST /api/auth/login": { status: 400, body: { detail: "Invalid credentials." } },
    });
    const user = userEvent.setup();
    const { router } = renderApp("/login");
    await user.type(await screen.findByLabelText("Username"), "marie");
    await user.type(screen.getByLabelText("Password"), "bad");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials.");
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled());
    expect(router.state.location.pathname).toBe("/login");
  });
});

describe("AppShell", () => {
  it("shows Admin only for staff", async () => {
    mockFetch({
      "GET /api/auth/me": { body: { ...staffUser, is_staff: false } },
      "GET /api/health": { body: health },
      "GET /api/dashboard": { body: dashboardFixture() },
    });
    renderApp("/");
    expect(await screen.findByText("Bonjour, marie")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  });
});
