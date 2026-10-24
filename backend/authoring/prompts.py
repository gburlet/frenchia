"""Versioned prompt templates for lesson authoring. Bump a version whenever its wording
changes: jobs record the versions they used (GenerationJob.prompts, lesson provenance)."""

PROMPT_VERSIONS = {
    "author.system": "2",
    "author.steps": "2",
    "author.revise": "1",
    "author.critic": "1",
}

SYSTEM = """\
You write original lessons for Frenchia, a French course for an English-speaking adult who is \
progressing from A1 to B2 and is learning Québec French.
Rules:
- Québec usage is the default. Use natural Québec vocabulary and phrasing in examples, dialogues \
and readings (e.g. souper, fin de semaine, magasiner, dépanneur), and mention the European French \
equivalent where it differs.
- Québec meals: déjeuner = breakfast, dîner = lunch, souper = supper. Say « la fin de semaine », \
not « le week-end ».
- Use standard language; mark familiar usage as familiar. Never use swear words or sacres.
- Write explanations in clear, friendly English with French examples. Keep French at or slightly \
below the lesson's CEFR level.
- Accuracy matters more than variety: every French sentence must be grammatical and natural, with \
correct accents, agreement and elision. Do not invent Québec expressions; when unsure, use \
standard French.
- Write original content; never reproduce textbook or website text."""

CONTEXT = """\
Lesson: {title} [{id}], CEFR {level}, kind: {kind}
Unit: {unit_title}
Learning objectives:
{objectives}
Grammar topics: {topics}
Vocabulary theme: {theme}
Québec angle: {quebec_focus}
Builds on: {prerequisites}
{lexicon}"""

LEXICON = """\
Verified Québec usage (authoritative; prefer these facts over your own memory):
{entries}
"""

SO_FAR = """\
The lesson so far (stay consistent with it; do not repeat it):
{summary}
"""

READING_WORDS = {"A1": "70-100", "A2": "110-150", "B1": "160-220", "B2": "220-300"}

STEPS = {
    "explanation": """\
Write the lesson's core explanation: a heading and a Markdown body of 150-300 words in English. \
Explain how to form and use the point, with short French examples in **bold**, and one or two \
pitfalls English speakers commonly hit. Also give the English translation of the lesson title.""",
    "table": """\
If a reference table genuinely helps (conjugation, forms, pronouns, articles...), produce it with \
2-5 columns and at most 12 rows; otherwise set include to false. Cells are short (no sentences).""",
    "examples": """\
Write 6-10 example sentences that illustrate the objectives, each with an English translation. \
Use everyday Québec situations. Set `region` = qc only when the sentence uses Québec-specific \
wording, common otherwise. Use `note` only for a remark about that same sentence, and never claim \
a Québec difference you are not certain of.""",
    "vocabulary": """\
List 10-16 vocabulary items for the theme, ordered from most to least useful. Give the bare word \
without article, its part of speech, the gender for every noun, Québec items with region qc and \
their formality, and a short French example with translation.""",
    "regional_note": """\
Write a short note (60-150 words, English) on how this lesson's topic is used in Québec compared \
with France, and up to 6 Québec/France/English variants. Only include differences you are certain \
of; use the verified Québec usage above. If there is no real difference, say so briefly and list \
no variants.""",
    "reading": """\
Write an original French reading passage of {words} words set in Québec that naturally uses the \
lesson's grammar and vocabulary, an English translation, and a glossary of 3-8 harder words. \
Write at CEFR {level}.""",
    "fill_blank": """\
Write {count} fill-in-the-blank items practising the objectives. Each French sentence contains \
exactly one ___ ; `answers` lists every correct fill (usually one). When the blank is a verb, \
`hint` is the infinitive in parentheses, e.g. (aller); otherwise a short English hint. The \
sentence must not contain the answer elsewhere.""",
    "translate_en_fr": """\
Write {count} short English sentences to translate into French, practising the objectives. For \
each, give 2-4 different correct French translations (include the natural Québec wording and a \
standard one when they differ) and a short hint.""",
    "translate_fr_en": """\
Write {count} short French sentences (natural Québec French) to translate into English, \
practising the objectives. For each, give 2-4 correct English translations and a short hint.""",
    "multiple_choice": """\
Write {count} multiple-choice questions (3-4 options, exactly one correct) testing the \
objectives. Questions and explanations in English, options in French where relevant. Wrong \
options should be plausible learner mistakes (wrong form, wrong auxiliary, wrong agreement), \
never the correct answer with different punctuation.""",
    "comprehension": """\
Write {count} multiple-choice comprehension questions about the reading passage below (3-4 \
options, exactly one correct, answerable from the text). Questions and options in simple French.
Passage:
{passage}""",
}

REPAIR = """\
Your previous answer had these problems:
{problems}
Produce a corrected answer that fixes every problem."""

REVISE = """\
Revise this part of the lesson according to the reviewer's notes. Keep everything that the \
notes do not ask to change. If the notes do not apply to this part, return it unchanged.
Reviewer notes:
{notes}
Current content (JSON):
{current}"""

CRITIC = """\
Proof-read this French sentence from a CEFR {level} exercise answer key. Learners will be graded \
against it, so it must be fully correct.
Sentence: {sentence}
List every problem. severity 'error' = anything a teacher would mark wrong (grammar, agreement, \
missing or wrong preposition, article, tense, spelling or accent, unnatural word choice); \
'minor' = acceptable but could be more natural. Québec usage and informal spoken forms are \
correct. Before concluding there are no errors, check verb constructions (parler à, penser à, \
téléphoner à), agreement, articles, prepositions and elision. Do not invent errors."""
