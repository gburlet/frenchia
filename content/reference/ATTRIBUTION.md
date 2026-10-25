# Attribution

## Lexique 3.83

`nouns.json` and `words.json` are derived from **Lexique 3.83** (http://www.lexique.org/).

> New, B., Pallier, C., Brysbaert, M., Ferrand, L. (2004). Lexique 2: A new French lexical database.
> *Behavior Research Methods, Instruments, & Computers*, 36(3), 516-524.

Lexique is licensed under **CC BY-SA 4.0** (https://creativecommons.org/licenses/by-sa/4.0/).
`nouns.json` (lemma, gender, frequency) is a derived/adapted dataset and is therefore distributed under the
same licence, CC BY-SA 4.0. Changes: filtered to common nouns (`NOM`), aggregated to lemma level, top 15,000 by
`freqlemfilms2`, gender collapsed to `m`/`f`/`mf`. `words.json` is every distinct word form (`ortho`),
lower-cased, under the same licence. The ranking of verb lemmas used to choose verbs for
`conjugations.json` also comes from Lexique.

## Conjugation generators

- **verbecc** 2.0.3, LGPL-3.0 (https://github.com/bretttolbert/verbecc): generated `conjugations.json`. Its data derives from the Verbiste project.
- **mlconjug3** 4.0.1, MIT (https://github.com/SekouDiaoNlp/mlconjug3): used only to cross-check simple tenses (`conjugation_disagreements.yaml`).

Both are build-time tools only; no library code is distributed with the data.
