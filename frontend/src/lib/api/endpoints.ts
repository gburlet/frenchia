import { api, ApiError } from "./client";
import type {
  AttemptRequest,
  AttemptResult,
  AudioClip,
  Curriculum,
  HealthResponse,
  Lesson,
  LessonProgress,
  LoginRequest,
  PracticeExercise,
  ProgressUpdate,
  TranslateFilters,
  TranslateOptions,
  User,
} from "./types";

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

/** Synthesize French speech (served from the server-side cache when already generated). */
export const createAudio = (body: { text: string; speed?: number }) =>
  api.post<AudioClip>("/api/audio", body);

// ---- Learning ----
export const fetchCurriculum = (signal?: AbortSignal) =>
  api.get<Curriculum>("/api/curriculum", signal);

export const fetchLesson = (id: string, signal?: AbortSignal) =>
  api.get<Lesson>(`/api/lessons/${encodeURIComponent(id)}`, signal);

export const updateProgress = (id: string, body: ProgressUpdate) =>
  api.post<LessonProgress>(`/api/lessons/${encodeURIComponent(id)}/progress`, body);

export const submitAttempt = (exerciseRevisionId: number, body: AttemptRequest) =>
  api.post<AttemptResult>(`/api/exercise-revisions/${exerciseRevisionId}/attempts`, body);

export const regradeAttempt = (attemptId: number) =>
  api.post<AttemptResult>(`/api/attempts/${attemptId}/regrade`);

export const disputeAttempt = (attemptId: number, comment?: string) =>
  api.post<{ disputed: boolean }>(
    `/api/attempts/${attemptId}/dispute`,
    comment ? { comment } : {},
  );

export const fetchTranslateOptions = (signal?: AbortSignal) =>
  api.get<TranslateOptions>("/api/practice/translate/options", signal);

export function translateNextPath(filters: TranslateFilters): string {
  const params = new URLSearchParams();
  if (filters.level) params.set("level", filters.level);
  if (filters.topic) params.set("topic", filters.topic);
  if (filters.direction) params.set("direction", filters.direction);
  const qs = params.toString();
  return `/api/practice/translate/next${qs ? `?${qs}` : ""}`;
}

export const fetchTranslateNext = (filters: TranslateFilters, signal?: AbortSignal) =>
  api.get<PracticeExercise>(translateNextPath(filters), signal);
