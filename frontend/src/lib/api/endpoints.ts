import { api, ApiError } from "./client";
import type { HealthResponse, LoginRequest, User } from "./types";

/** Returns the current user, or null when logged out (401/403). */
export async function fetchMe(signal?: AbortSignal): Promise<User | null> {
  try {
    return await api.get<User>("/api/auth/me", signal);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      return null;
    }
    throw error;
  }
}

export const login = (credentials: LoginRequest) =>
  api.post<User>("/api/auth/login", credentials);

export const logout = () => api.post<void>("/api/auth/logout");

/** A 503 still carries a useful body (status "degraded"), so return it. */
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  try {
    return await api.get<HealthResponse>("/api/health", signal);
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status === 503 &&
      error.body &&
      typeof error.body === "object" &&
      "services" in error.body
    ) {
      return error.body as HealthResponse;
    }
    throw error;
  }
}
