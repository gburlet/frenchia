import { api } from "./client";

export type VocabPos = "noun" | "verb" | "adjective" | "adverb" | "expression" | "other";
export type VocabStatus = "not_started" | "elsewhere" | "new" | "learning" | "due";
export type CheckResult = "correct" | "accent" | "article" | "gender" | "incorrect";
export type Rating = 1 | 2 | 3 | 4;

export interface Lexeme {
  id: number;
  fr: string;
  display: string;
  article: string;
  en: string;
  pos: VocabPos;
  gender: "f" | "m" | null;
  plural: string | null;
  region: "qc" | "fr" | "common";
  formality: "standard" | "familiar" | "formal";
  example_fr: string | null;
  example_en: string | null;
  note: string | null;
  set: string;
}

export interface VocabSetSummary {
  slug: string;
  kind: "theme" | "lesson";
  level: string;
  title: string;
  title_en: string;
  lesson: string | null;
  size: number;
  in_deck: number;
  seen: number;
  due: number;
}

export interface VocabStats {
  cards: number;
  words: number;
  due_now: number;
  due_today: number;
  new_waiting: number;
  new_remaining_today: number;
  new_today: number;
  reviews_today: number;
  mature: number;
}

export interface VocabSets {
  sets: VocabSetSummary[];
  stats: VocabStats;
}

export interface VocabSetDetail {
  slug: string;
  kind: "theme" | "lesson";
  level: string;
  title: string;
  title_en: string;
  lesson: string | null;
  words: (Lexeme & { status: VocabStatus })[];
}

export interface ReviewCard {
  id: number;
  direction: "recognize" | "recall";
  is_new: boolean;
  due: string;
  lexeme: Lexeme;
  previews: Record<"1" | "2" | "3" | "4", number>;
}

export interface ReviewBatch {
  cards: ReviewCard[];
  due_count: number;
  new_remaining_today: number;
  next_due: string | null;
}

export interface CheckResponse {
  result: CheckResult;
  correct: boolean;
  expected: string;
  message: string;
  suggested_rating: Rating;
}

export interface ReviewPayload {
  rating: Rating;
  duration_ms?: number;
  answer?: string;
  check_result?: CheckResult;
}

export const fetchVocabSets = (signal?: AbortSignal) => api.get<VocabSets>("/api/vocab/sets", signal);
export const fetchVocabSet = (slug: string, signal?: AbortSignal) =>
  api.get<VocabSetDetail>(`/api/vocab/sets/${encodeURIComponent(slug)}`, signal);
export const learnVocabSet = (slug: string) =>
  api.post<{ added: number; skipped: number }>(`/api/vocab/sets/${encodeURIComponent(slug)}/learn`);
export const removeVocabSet = (slug: string) =>
  api.post<{ removed: number }>(`/api/vocab/sets/${encodeURIComponent(slug)}/remove`);
export const addVocabWord = (lexemeId: number) =>
  api.post<{ lexeme: number; added: boolean }>(`/api/vocab/words/${lexemeId}/add`);
export const removeVocabLexeme = (lexemeId: number) =>
  api.post<{ lexeme: number; removed: boolean }>(`/api/vocab/words/${lexemeId}/remove`);
export const fetchVocabReview = (ahead: boolean, signal?: AbortSignal, limit = 20) =>
  api.get<ReviewBatch>(`/api/vocab/review?limit=${limit}${ahead ? "&ahead=1" : ""}`, signal);
export const checkVocabCard = (id: number, answer: string) =>
  api.post<CheckResponse>(`/api/vocab/cards/${id}/check`, { answer });
export const removeVocabWord = (id: number, removed = true) =>
  api.post<{ lexeme: number; removed: boolean }>(`/api/vocab/cards/${id}/remove`, { removed });
export const reviewVocabCard = (id: number, payload: ReviewPayload) =>
  api.post<{ id: number; due: string; interval_seconds: number }>(`/api/vocab/cards/${id}/review`, payload);
