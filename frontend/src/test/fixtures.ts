import type { Dashboard } from "@/lib/api/progress";
import type { AttemptResult, Curriculum, Lesson } from "@/lib/api/types";

export const curriculumFixture: Curriculum = {
  levels: [
    { level: "A1", title: "Débutant", summary: "First steps.", units: [] },
    {
      level: "A2",
      title: "Élémentaire",
      summary: "Everyday situations.",
      units: [
        {
          id: "a2-u01-past",
          title: "Raconter au passé",
          objectives: ["Tell what happened"],
          lessons: [
            {
              id: "a2-passe-compose-er",
              title: "Le passé composé des verbes en -er",
              kind: "grammar",
              published: true,
              progress: { status: "in_progress", completed_at: null },
            },
            {
              id: "a2-passe-compose-etre",
              title: "Le passé composé avec être",
              kind: "grammar",
              published: true,
              progress: { status: "completed", completed_at: "2026-10-01T00:00:00Z" },
            },
            {
              id: "a2-imparfait",
              title: "L’imparfait",
              kind: "grammar",
              published: false,
              progress: { status: "not_started", completed_at: null },
            },
          ],
        },
      ],
    },
    { level: "B1", title: "Intermédiaire", summary: "Opinions.", units: [] },
    { level: "B2", title: "Avancé", summary: "Nuance.", units: [] },
  ],
};

export const lessonFixture: Lesson = {
  id: "a2-passe-compose-er",
  title: "Le passé composé des verbes en -er",
  title_en: "The passé composé of -er verbs",
  level: "A2",
  unit: { id: "a2-u01-past", title: "Raconter au passé" },
  objectives: ["Form the passé composé"],
  estimated_minutes: 33,
  grammar_topics: [{ id: "passe-compose-avoir", title: "Passé composé with avoir" }],
  revision: { id: 12, content_version: 2 },
  sections: [
    { type: "explanation", id: "intro", heading: "Le principe", body: "Use **avoir** plus the *participe passé*.\n\n- item one\n- item two\n\n<b>raw</b>" },
    {
      type: "examples",
      id: "exemples",
      heading: "Exemples",
      examples: [
        { fr: "J’ai mangé une poutine.", en: "I ate a poutine.", note: "Très québécois", region: "qc" },
        { fr: "Elle a parlé.", en: "She spoke." },
      ],
    },
    {
      type: "table",
      id: "conjugaison",
      heading: "Conjugaison",
      caption: "Parler au passé composé",
      columns: ["Sujet", "Forme"],
      rows: [["je", "j’ai parlé"], ["tu", "tu as parlé"]],
    },
    {
      type: "vocabulary",
      id: "vocab",
      heading: "Vocabulaire",
      items: [
        { fr: "livre", en: "book", pos: "noun", gender: "m", region: "common", formality: "standard", example_fr: "Un livre.", example_en: "A book." },
        { fr: "école", en: "school", pos: "noun", gender: "f" },
        { fr: "char", en: "car", pos: "noun", gender: "m", region: "qc", formality: "familiar" },
      ],
    },
    {
      type: "reading",
      id: "reading",
      title: "Ma fin de semaine",
      passage_fr: "Samedi, j’ai marché. Ensuite, j’ai mangé !",
      translation_en: "On Saturday I walked. Then I ate!",
      glossary: [{ fr: "marcher", en: "to walk", pos: "verb" }],
    },
    {
      type: "regional_note",
      id: "note",
      heading: "Au Québec",
      body: "Au Québec, on dit **char**.",
      variants: [{ qc: "un char", fr: "une voiture", en: "a car" }],
    },
  ],
  exercises: [
    { exercise_revision_id: 41, id: "ex-04", type: "fill_blank", sentence: "Elle ___ à son ami.", hint: "(parler)", translation_en: "She spoke to her friend." },
    { exercise_revision_id: 42, id: "ex-05", type: "translate", direction: "en_fr", prompt: "I watched a movie.", hint: "regarder" },
  ],
  progress: { status: "in_progress", completed_at: null },
  previous: { id: "a2-prev", title: "Leçon précédente" },
  next: { id: "a2-next", title: "Leçon suivante" },
};

export function attemptResult(overrides: Partial<AttemptResult> = {}): AttemptResult {
  return {
    attempt_id: 7,
    status: "graded",
    verdict: "correct",
    score: 100,
    grading: "deterministic",
    correct_answer: "Elle a parlé à son ami.",
    accepted_answers: ["Elle a parlé à son ami."],
    feedback: { summary: "Bravo!", errors: [], corrected: null, register_note: null, accent_only: false },
    explanation: null,
    model: null,
    ...overrides,
  };
}

export function dashboardFixture(overrides: Partial<Dashboard> = {}): Dashboard {
  const history = Array.from({ length: 14 }, (_, i) => ({
    date: `2026-10-${String(12 + i).padStart(2, "0")}`,
    items: i === 13 ? 12 : i % 3,
    minutes: i === 13 ? 9 : 1,
    by_kind: i === 13 ? { exercises: 8, vocab: 4 } : {},
  }));
  return {
    today: "2026-10-25",
    streak: { current: 3, longest: 7, studied_today: true },
    minutes: { today: 9, week: 41 },
    accuracy_week: { graded: 20, accuracy: 0.75 },
    history,
    lessons: { published: 6, completed: 2 },
    vocab: {
      cards: 40, words: 20, due_now: 5, due_today: 8, new_waiting: 10, new_today: 10,
      new_remaining_today: 10, reviews_today: 3, mature: 2,
    },
    topics: [
      { id: "passe-compose-etre", title: "Passé composé with être", level: "A2", attempts: 6, accuracy: 0.42, last_practiced: null },
      { id: "imparfait", title: "Imparfait", level: "A2", attempts: 4, accuracy: 0.9, last_practiced: null },
    ],
    weak_topics: [
      {
        id: "passe-compose-etre", title: "Passé composé with être", level: "A2", accuracy: 0.42,
        attempts: 6, recent_mistakes: 2, reason: "42% recent accuracy over 6 tries; 2 mistakes in the last 3 weeks",
      },
    ],
    verb_tenses: [{ tense: "passe_compose", label: "Passé composé", attempts: 10, accuracy: 0.6 }],
    mistakes: [{ category: "auxiliary", count: 3 }],
    review: null,
    ...overrides,
  };
}
