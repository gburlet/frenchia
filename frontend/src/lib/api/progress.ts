import { api } from "./client";
import type { PublicExercise } from "./types";
import type { VocabStats } from "./vocab";

export interface TopicStat {
  id: string;
  title: string;
  level: string;
  attempts: number;
  /** Recent-weighted accuracy, 0-1. */
  accuracy: number;
  last_practiced: string | null;
}

export interface WeakTopic {
  id: string;
  title: string;
  level: string;
  accuracy: number | null;
  attempts: number;
  recent_mistakes: number;
  reason: string;
}

export interface DayActivity {
  date: string;
  items: number;
  minutes: number;
  by_kind: Partial<Record<"exercises" | "verbs" | "vocab", number>>;
}

export type ExtrasStatus = "none" | "queued" | "running" | "ready" | "failed";

export interface ReviewSummary {
  id: number;
  items: number;
  answered: number;
  extras: ExtrasStatus;
}

export interface Dashboard {
  today: string;
  streak: { current: number; longest: number; studied_today: boolean };
  minutes: { today: number; week: number };
  accuracy_week: { graded: number; accuracy: number | null };
  history: DayActivity[];
  lessons: { published: number; completed: number };
  vocab: VocabStats;
  topics: TopicStat[];
  weak_topics: WeakTopic[];
  verb_tenses: { tense: string; label: string; attempts: number; accuracy: number }[];
  mistakes: { category: string; count: number }[];
  review: ReviewSummary | null;
}

export type ItemSource = "missed" | "unseen" | "refresh" | "generated";

export interface ReviewItem {
  exercise: PublicExercise;
  topic: { id: string; title: string };
  source: ItemSource;
  source_label: string;
  ai_generated: boolean;
  lesson: { id: string; title: string };
  /** Verdict of the latest answer in this set, "pending" while ungraded, null if unanswered. */
  result: "correct" | "acceptable" | "incorrect" | "pending" | null;
}

export interface ReviewSet {
  id: number;
  created_at: string;
  completed_at: string | null;
  topics: WeakTopic[];
  extras: ExtrasStatus;
  items: ReviewItem[];
}

export interface ReviewState {
  current: ReviewSet | null;
  weak_topics: WeakTopic[];
}

export const fetchDashboard = (signal?: AbortSignal) => api.get<Dashboard>("/api/dashboard", signal);
export const fetchReview = (signal?: AbortSignal) => api.get<ReviewState>("/api/review", signal);
export const startReview = () => api.post<ReviewSet>("/api/review");
export const completeReview = (id: number) => api.post<ReviewSet>(`/api/review/${id}/complete`);
