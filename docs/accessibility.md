# Accessibility

Target: WCAG 2.2 AA for one learner using a keyboard, a screen reader or both.

## What is checked automatically

- `frontend/src/test/a11y.test.tsx` runs **axe-core** on the dashboard, curriculum, a lesson,
  the Translation Station, vocabulary, review, progress and login pages, using mocked API data.
  Any violation fails `just check`.
- jsdom has no layout, so axe can't check **colour contrast** there. Contrast is enforced in the
  colour tokens instead (`docs/style-guide.md`). Every text colour is at least 4.5:1 on the
  page, header and card backgrounds, and so is white text on every filled button and badge.
  Re-check any new token before using it for text.

## Conventions

- Every page has one `h1`, and headings don't skip levels. `ExerciseCard` takes
  `headingLevel={2}` where it sits directly under the page title.
- Charts are a single series in one colour, with a visible label on the latest value, a tooltip
  on hover **and keyboard focus**, an `aria-label` per column and a "Show as table" view.
  Accuracy bars are `role="meter"` with a text value next to them.
- AI-generated content is labelled in text ("AI-generated"), never by colour alone.
- Loading states are `role="status"`, errors `role="alert"`. A page that crashes or fails to
  load shows an error with Reload, and the header and navigation stay usable.
- Animations respect `prefers-reduced-motion`.

## Keyboard

Press `?` anywhere for the list of shortcuts:
- `g` then a letter goes to a page;
- `t` toggles the tutor;
- `Enter` checks an answer;
- `1`–`4` pick an option or rate a flashcard.

The single-key shortcuts can be switched off in that dialog (WCAG 2.1.4). None of them fire
while you are typing in a text box.
