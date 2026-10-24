import { describe, expect, it } from "vitest";
import { ApiError, apiFetch } from "./client";
import { mockFetch } from "@/test/mockFetch";

describe("apiFetch", () => {
  it("attaches X-CSRFToken from the cookie on POST", async () => {
    document.cookie = "csrftoken=abc123; path=/";
    const fetchMock = mockFetch({ "POST /api/auth/logout": { status: 204 } });
    await apiFetch("/api/auth/logout", { method: "POST" });
    const init = fetchMock.mock.calls[0]![1]!;
    expect((init.headers as Record<string, string>)["X-CSRFToken"]).toBe("abc123");
    expect(init.credentials).toBe("same-origin");
  });

  it("fetches the csrf cookie first when missing", async () => {
    const fetchMock = mockFetch({
      "GET /api/auth/csrf": () => {
        document.cookie = "csrftoken=fresh; path=/";
        return { status: 204 };
      },
      "POST /api/auth/login": { body: {} },
    });
    await apiFetch("/api/auth/login", { method: "POST", body: { a: 1 } });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/auth/csrf");
    const init = fetchMock.mock.calls[1]![1]!;
    expect((init.headers as Record<string, string>)["X-CSRFToken"]).toBe("fresh");
  });

  it("does not send a CSRF header on GET", async () => {
    const fetchMock = mockFetch({ "GET /api/health": { body: {} } });
    await apiFetch("/api/health");
    const init = fetchMock.mock.calls[0]![1]!;
    expect(init.headers).not.toHaveProperty("X-CSRFToken");
  });

  it("throws ApiError with status and detail", async () => {
    mockFetch({ "GET /api/x": { status: 400, body: { detail: "Nope" } } });
    await expect(apiFetch("/api/x")).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      detail: "Nope",
    });
    await expect(apiFetch("/api/x")).rejects.toBeInstanceOf(ApiError);
  });
});
