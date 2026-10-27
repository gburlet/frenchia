const SPACE = /[\s\u00a0\u202f]/;
const CLOSERS = new Set(["»", "”", '"', ")", "’", "'"]);
const ABBREVIATIONS = new Set([
  "m",
  "mm",
  "mme",
  "mmes",
  "mlle",
  "mlles",
  "dr",
  "dre",
  "pr",
  "me",
  "st",
  "ste",
  "sr",
  "jr",
  "p",
  "pp",
  "ex",
  "etc",
  "cf",
  "env",
  "no",
  "n",
  "vol",
  "chap",
  "fig",
  "av",
  "apr",
  "boul",
  "c.-à-d",
  "p. ex",
  "vs",
  "ch",
  "tél",
  "min",
  "max",
  "rés",
]);

function isAbbreviation(before: string): boolean {
  const match = /([\p{L}.-]+)$/u.exec(before);
  if (!match) return false;
  const word = match[1]!.toLowerCase();
  if (ABBREVIATIONS.has(word)) return true;
  // A lone capital initial ("J. Tremblay").
  return /^\p{Lu}$/u.test(match[1]!);
}

function splitParagraph(text: string): string[] {
  const out: string[] = [];
  let start = 0;
  let i = 0;
  while (i < text.length) {
    const ch = text[i]!;
    if (ch !== "." && ch !== "!" && ch !== "?" && ch !== "…") {
      i++;
      continue;
    }
    let end = i + 1;
    while (end < text.length && /[.!?…]/.test(text[end]!)) end++;
    const isPeriod = ch === ".";
    let closed = false;
    // Optional closing guillemet/quote, possibly after a (narrow) space: « Bonjour ! »
    let j = end;
    while (j < text.length && SPACE.test(text[j]!)) j++;
    if (
      j < text.length &&
      CLOSERS.has(text[j]!) &&
      (j === end || text[j] === "»")
    ) {
      end = j + 1;
      closed = true;
      while (end < text.length && CLOSERS.has(text[end]!)) end++;
    } else if (end < text.length && CLOSERS.has(text[end]!)) {
      end++;
      closed = true;
    }
    const atEnd = end >= text.length;
    const spaced = !atEnd && SPACE.test(text[end]!);
    if (!atEnd && !spaced) {
      i = end;
      continue;
    }
    if (isPeriod && end === i + 1 && isAbbreviation(text.slice(start, i))) {
      i = end;
      continue;
    }
    if (!atEnd) {
      let k = end;
      while (k < text.length && SPACE.test(text[k]!)) k++;
      const next = text[k];
      if (closed && next && /\p{Ll}/u.test(next)) {
        i = end;
        continue;
      }
    }
    const piece = text.slice(start, end).trim();
    if (piece) out.push(piece);
    start = end;
    i = end;
  }
  const rest = text.slice(start).trim();
  if (rest) out.push(rest);
  return out;
}

/** Splits French prose into sentences for per-sentence playback. */
export function splitSentences(text: string): string[] {
  return text.split(/\n+/).flatMap((paragraph) => splitParagraph(paragraph));
}

/** "un"/"une"/"l'" prefix for a noun, based on gender and the first letter. */
export function withArticle(
  word: string,
  gender: "m" | "f" | null | undefined,
  isNoun: boolean,
): string {
  // Proper nouns (le Vieux-Québec) don't take un/une; the gender pill still shows the gender.
  if (!isNoun || !gender || /^\p{Lu}/u.test(word)) return word;
  const first = word
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .charAt(0)
    .toLowerCase();
  // Mute h can't be told from aspirated h without a dictionary, so h-words get un/une.
  if ("aeiou".includes(first)) return `l’${word}`;
  return `${gender === "f" ? "une" : "un"} ${word}`;
}

/** Lesson text without its **bold** markers (for labels and speech). */
export function stripBold(text: string): string {
  return text.replace(/\*+/g, "");
}
