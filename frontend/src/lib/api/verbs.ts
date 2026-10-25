import { api } from "./client";

export type Auxiliary = "avoir" | "être" | "both";
export type DrillMode = "form" | "context" | "mixed";
export type AnswerMode = "form" | "table" | "context";
export type AnswerResultKind = "correct" | "accent" | "incorrect";

export interface VerbTense {
  key: string;
  label: string;
  label_en: string;
  level: string;
  mood: string;
  compound: boolean;
  drill: boolean;
}

export interface VerbSet {
  id: string;
  title: string;
  title_en: string;
  level: string;
  description: string;
  verbs: string[];
  tenses: string[];
}

export interface VerbSummary {
  infinitive: string;
  slug: string;
  en: string | null;
  group: number;
  auxiliary: Auxiliary;
  pronominal: boolean;
  sentences: number;
  sets: string[];
}

export interface VerbIndex {
  tenses: VerbTense[];
  sets: VerbSet[];
  verbs: VerbSummary[];
}

export interface TableRow {
  person: string;
  form: string;
  variants: string[];
  said: string;
}

export interface TenseTable {
  tense: string;
  label: string;
  label_en: string;
  mood: string;
  level: string;
  rows: TableRow[];
}

export interface VerbExample {
  tense: string;
  tense_label: string;
  person: string;
  fr: string;
  en: string;
  form: string;
  region: string;
}

export interface VerbMastery {
  tense: string;
  attempts: number;
  ewma: number;
}

export interface VerbDetail extends VerbSummary {
  note: string | null;
  participle_past: string;
  participle_present: string;
  table: TenseTable[];
  examples: VerbExample[];
  mastery: VerbMastery[];
}

export interface SentenceRef {
  bank: string;
  version: number;
  index: number;
}

export interface DrillSentence extends SentenceRef {
  before: string;
  after: string;
  en: string;
  region: string;
}

export interface DrillItem {
  infinitive: string;
  slug: string;
  en: string | null;
  tense: string;
  tense_label: string;
  person: string;
  subject: string;
  mode: "form" | "context";
  sentence: DrillSentence | null;
}

export interface DrillRequest {
  set?: string;
  verbs?: string[];
  tenses: string[];
  persons?: string[];
  mode?: DrillMode;
  count?: number;
}

export interface VerbAnswer {
  infinitive: string;
  tense: string;
  person: string;
  answer: string;
  mode: AnswerMode;
  sentence?: SentenceRef;
  time_spent_ms?: number;
}

export interface VerbAnswerResult {
  result: AnswerResultKind;
  correct: boolean;
  expected: string;
  accepted: string[];
  diagnosis: string;
  message: string;
  said: string;
}

export interface WeakSpot {
  infinitive: string;
  slug: string;
  tense: string;
  tense_label: string;
  attempts: number;
  ewma: number;
}

export interface VerbProgress {
  attempts: number;
  correct: number;
  verbs_practiced: number;
  weak_spots: WeakSpot[];
}

export const fetchVerbIndex = (signal?: AbortSignal) => api.get<VerbIndex>("/api/verbs", signal);
export const fetchVerb = (slug: string, signal?: AbortSignal) =>
  api.get<VerbDetail>(`/api/verbs/${encodeURIComponent(slug)}`, signal);
export const fetchVerbProgress = (signal?: AbortSignal) =>
  api.get<VerbProgress>("/api/verbs/progress", signal);
export const createDrill = (body: DrillRequest) => api.post<{ items: DrillItem[] }>("/api/verbs/drills", body);
export const submitVerbAnswers = (answers: VerbAnswer[]) =>
  api.post<{ results: VerbAnswerResult[] }>("/api/verbs/answers", { answers });
