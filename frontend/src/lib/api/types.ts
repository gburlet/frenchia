// Hand-written to match the backend contract until `npm run api:types`
// generates src/lib/api/schema.d.ts.
export interface User {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export type ServiceStatus = "ok" | "error" | (string & {});

export interface HealthResponse {
  status: "ok" | "degraded" | (string & {});
  services: Record<string, ServiceStatus>;
  version: string;
}

export interface AudioClip {
  key: string;
  url: string;
  cached: boolean;
}

// ---- Learning API (docs/api-learning.md) ----
export type Level = "A1" | "A2" | "B1" | "B2";
export type LessonStatus = "not_started" | "in_progress" | "completed";
export type Region = "qc" | "fr" | "common";

export interface LessonProgress {
  status: LessonStatus;
  completed_at: string | null;
}

export interface CurriculumLesson {
  id: string;
  title: string;
  kind: string;
  published: boolean;
  progress: LessonProgress;
}
export interface CurriculumUnit {
  id: string;
  title: string;
  objectives: string[];
  lessons: CurriculumLesson[];
}
export interface CurriculumLevel {
  level: Level;
  title: string;
  summary: string;
  units: CurriculumUnit[];
}
export interface Curriculum {
  levels: CurriculumLevel[];
}

export interface ExplanationSection {
  type: "explanation";
  id: string;
  heading: string;
  body: string;
}
export interface ExampleItem {
  fr: string;
  en: string;
  note?: string | null;
  region?: Region;
}
export interface ExamplesSection {
  type: "examples";
  id: string;
  heading: string;
  examples: ExampleItem[];
}
export interface TableSection {
  type: "table";
  id: string;
  heading: string;
  columns: string[];
  rows: string[][];
  caption?: string | null;
}
export interface VocabItem {
  fr: string;
  en: string;
  pos: "noun" | "verb" | "adjective" | "adverb" | "expression" | "other";
  gender?: "m" | "f" | null;
  region?: Region;
  formality?: "formal" | "standard" | "familiar";
  example_fr?: string | null;
  example_en?: string | null;
}
export interface VocabularySection {
  type: "vocabulary";
  id: string;
  heading: string;
  items: VocabItem[];
}
export interface ReadingSection {
  type: "reading";
  id: string;
  title: string;
  passage_fr: string;
  translation_en: string;
  glossary?: VocabItem[];
}
export interface RegionalVariant {
  qc: string;
  fr: string;
  en: string;
  formality?: string | null;
}
export interface RegionalNoteSection {
  type: "regional_note";
  id: string;
  heading: string;
  body: string;
  variants?: RegionalVariant[];
}
export type LessonSection =
  | ExplanationSection
  | ExamplesSection
  | TableSection
  | VocabularySection
  | ReadingSection
  | RegionalNoteSection;

export interface PublicExerciseBase {
  exercise_revision_id: number;
  id: string;
}
export interface TranslateExercise extends PublicExerciseBase {
  type: "translate";
  direction: "en_fr" | "fr_en";
  prompt: string;
  hint?: string | null;
}
export interface FillBlankExercise extends PublicExerciseBase {
  type: "fill_blank";
  sentence: string;
  hint?: string | null;
  translation_en?: string | null;
}
export interface MultipleChoiceExercise extends PublicExerciseBase {
  type: "multiple_choice";
  question: string;
  options: string[];
}
export interface ComprehensionExercise extends PublicExerciseBase {
  type: "comprehension";
  reading_id: string;
  question: string;
  options: string[];
}
export type PublicExercise =
  | TranslateExercise
  | FillBlankExercise
  | MultipleChoiceExercise
  | ComprehensionExercise;

export interface LessonRef {
  id: string;
  title: string;
}
export interface Lesson {
  id: string;
  title: string;
  title_en: string;
  level: Level;
  unit: LessonRef;
  objectives: string[];
  estimated_minutes: number;
  grammar_topics: LessonRef[];
  revision: { id: number; content_version: number };
  sections: LessonSection[];
  exercises: PublicExercise[];
  progress: LessonProgress;
  previous: LessonRef | null;
  next: LessonRef | null;
}

export interface ProgressUpdate {
  completed?: boolean;
}

export type Verdict = "correct" | "acceptable" | "incorrect";
export interface FeedbackError {
  category: string;
  severity: string;
  span: string;
  explanation: string;
}
export interface Feedback {
  summary: string;
  errors: FeedbackError[];
  corrected: string | null;
  register_note: string | null;
  accent_only: boolean;
}
export interface AttemptRequest {
  answer: string | number;
  time_spent_ms?: number;
}
export interface AttemptResult {
  attempt_id: number;
  status: "graded" | "pending" | (string & {});
  verdict: Verdict | null;
  score: number | null;
  grading: "deterministic" | "llm" | "pending";
  correct_answer: string | null;
  accepted_answers: string[];
  correct_index?: number | null;
  feedback: Feedback;
  explanation: string | null;
  model: string | null;
}

export interface TranslateOptions {
  levels: Level[];
  topics: { id: string; title: string; level: Level; count: number }[];
}
export type TranslateDirection = "en_fr" | "fr_en";
export interface TranslateFilters {
  level?: string;
  topic?: string;
  direction?: string;
}
export interface PracticeExercise extends TranslateExercise {
  lesson: { id: string; title: string; level: Level };
}
