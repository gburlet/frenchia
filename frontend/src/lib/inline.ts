// Generated lesson text uses Markdown emphasis in short fields too (hints, notes, examples,
// options), and not always well-formed: « je parler****ai », « *Je doute **qu'**il* ».

export interface InlinePart {
  text: string;
  bold: boolean;
  italic: boolean;
}

const BOLD = /\*\*(.+?)\*\*/g;
const ITALIC = /\*([^*\s](?:[^*]*[^*\s])?)\*/g;

/** Text split into plain, **bold** and *italic* runs; stray asterisks are dropped. */
export function inlineParts(text: string): InlinePart[] {
  const merged = text.replace(/(\S)\*{4}(?=\S)/g, "$1"); // two bold runs back to back
  const parts: InlinePart[] = [];
  merged.split(BOLD).forEach((segment, i) => {
    if (i % 2) {
      parts.push({ text: dropStars(segment), bold: true, italic: false });
      return;
    }
    segment.split(ITALIC).forEach((piece, j) => {
      parts.push({
        text: j % 2 ? piece : dropStars(piece),
        bold: false,
        italic: j % 2 === 1,
      });
    });
  });
  return parts.filter((p) => p.text);
}

/** A lone * left from emphasis the model never closed (or nested in a way Markdown can't parse). */
function dropStars(text: string): string {
  return text.replace(/\*/g, "");
}

/** A heading field is rendered as a heading already: « ## Formation » → « Formation ». */
export function cleanHeading(text: string): string {
  return text.replace(/^\s*#{1,6}\s*/, "").trim();
}
