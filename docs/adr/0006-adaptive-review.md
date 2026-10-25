# ADR 0006: Adaptive review and the dashboard

- Status: accepted
- Date: 2026-10-25

## Context

Phase 7 adds a dashboard (streak, time, accuracy by topic, due reviews, weak topics) and
personalized review sets: rules pick the learner's weak topics and recent mistakes, and the
result is a mix of existing exercises and new ones the local LLM writes. The plan asks for the
new ones to be auto-validated and labelled "AI-generated".

## Decisions

### Dashboard numbers are computed, not tracked
- `progress/stats.py` derives everything from tables that already exist: `ExerciseAttempt`,
  `ConjugationAttempt`, `VocabReview`, `TopicMastery`, `VerbMastery`, `MistakeOccurrence`.
  There is no `StudySession` table. The plan proposed one, but nothing it would record is
  missing from the activity rows.
- A study day is a local calendar day (`TIME_ZONE`, America/Edmonton) with at least one graded
  exercise, verb answer or flashcard review. The streak survives until the end of the next day,
  so "studied yesterday, not yet today" still shows the streak.
- Study time is the time spent on those items, each capped at 3 minutes so a tab left open
  doesn't count as study. Reading a lesson isn't timed.
- Weekly accuracy counts graded exercises and verb answers. Flashcards are self-rated, so they
  don't count towards it.
- One request, about 70 ms with real data.

### Weak topics are a rule, not a model
- A topic is weak when its recent-weighted accuracy (`TopicMastery.ewma`) is below 0.8 after
  at least 2 answers, or it has mistakes from the last 3 weeks.
- The score is `(1 - ewma) + 0.1 × min(mistakes, 5)`, and the top 3 topics are used. Each comes
  with a plain-English reason ("42% recent accuracy over 6 tries; 2 mistakes in the last 3
  weeks").
- A learner with no weak spots reviews the topics of the lessons they've opened.

### A review set never waits for the LLM
- `POST /api/review` builds the set immediately (in about 30 ms) from published curriculum
  exercises on the weak topics. About 9 items are split across the topics, ranked:
  1. answered wrong last time;
  2. never tried;
  3. least recently tried.
- Comprehension questions are left out, because they need their reading passage.
- Starting a new set closes any unfinished one.
- Then a background task asks the local LLM for new exercises on the 2 weakest topics:
  2 fill-in-the-blanks and 2 English→French translations each. The prompt is grounded in the
  published lesson that teaches the topic and in the learner's recent wrong answers. The items
  are appended to the set as they pass.
- The page polls while the extras are being written, so the learner starts practising straight
  away.
- The task runs on its own queue ("practice") with its own worker (`practice-worker`), so it
  never waits behind a batch of lesson generation. The two share the LLM call by call.
  Measured at about 2–6 minutes per set, depending on whether lesson generation is running.

### Generated exercises: a stricter bar, because nobody reviews them first
- They use the same generator code, the same deterministic lesson checks and the one repair
  round as lesson exercises.
- Then the AI critic proof-reads every French sentence a learner is graded against. Any item it
  flags is **dropped**, not reported.
- An item that repeats one of the lesson's exercises is dropped.
- What was dropped, and why, is kept on the set (`extras_log`, visible in Admin).
- They are stored as immutable `ExerciseRevision`s with `origin=personalized`, attached to the
  lesson's published revision. Attempts, grading, mastery, mistakes and the tutor work on them
  unchanged.
- They are never part of a lesson. The lesson API, the Translation Station and the "accept
  disputed answer" flow all filter on `origin=curriculum`.
- Later review sets can reuse a learner's own earlier generated items.
- The UI labels them "AI-generated", with a tooltip saying they were checked automatically,
  not by a teacher.

## Consequences

- The critic sometimes rejects good sentences (it has flagged « pour la fin de semaine »), so a
  set can get fewer extras than requested. That's the intended trade-off.
- Personalized exercise rows accumulate per set. They are small, but there is no pruning yet.
