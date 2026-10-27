// Generated lessons sometimes write line breaks as « <br> », « ⟩⟩⟩ » or « ⏎ » (and leave HTML
// comments); with raw HTML disabled these would show as text and flatten tables.
const LINE_BREAK = /<br\s*\/?>|<br-\s?|⟩{2,}|⏎/gi;
const HTML_COMMENT = /<!--[\s\S]*?-->/g;
const TABLE_RULE = /\|\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|/;

/** « text | A | B | |---|---| | a | b | » (a table run into one line) -> one row per line. */
function splitTable(line: string): string {
  const rule = TABLE_RULE.exec(line);
  if (!rule) return line;
  const columns = (rule[0].match(/\|/g) ?? []).length - 1;
  const start = line.indexOf("|");
  const end = line.lastIndexOf("|");
  const cells = line.slice(start + 1, end).split("|");
  const rows: string[] = [];
  let i = 0;
  while (i < cells.length) {
    rows.push(`| ${cells.slice(i, i + columns).map((c) => c.trim()).join(" | ")} |`);
    i += columns;
    if (i < cells.length && !cells[i]?.trim()) i += 1; // the « | | » between two rows
  }
  return [line.slice(0, start).trim(), rows.join("\n"), line.slice(end + 1).trim()]
    .filter(Boolean)
    .join("\n\n");
}

// gpt-oss sometimes writes a whole body on one line, with two spaces where the line breaks
// were (same repair as tidy() in the backend, for lessons published before it).
export function cleanMarkdown(text: string): string {
  let out = text.replace(HTML_COMMENT, "").replace(LINE_BREAK, "\n");
  if (!out.includes("\n")) out = out.replace(/ {2,}/g, "\n\n");
  out = out.replace(/\*{5,}/g, "**"); // « *****Heading** »: a rule run into a bold heading
  out = out.replace(/(\S)\*{4}(?=\S)/g, "$1"); // « je parler****ai »: two bold runs back to back
  // « …participe.  ## Formation  ### 1. Auxiliaire  - avoir »: breaks flattened into two spaces
  // in a body that still has some newlines elsewhere.
  // The gap may mix spaces with no-break or zero-width ones (« travail. \u202f##\u202fFormation »),
  // and a heading may follow a sentence after a single space (« viendras… ### Quick tip »).
  out = out.replace(/(\S)[ \t\u00a0\u202f\u200b-\u200d\u2060\ufeff]{2,}(?=#{1,6}[ \u00a0\u202f]|[-*] |\d+\. )/g, "$1\n\n");
  out = out.replace(/([.!?…:]\*{0,3})[ \u00a0\u202f]\*{0,3}(?=#{2,6}[ \u00a0\u202f])/g, "$1\n\n");
  out = out.replace(/^(#{1,6})[\u00a0\u202f]+/gm, "$1 ");
  // « **### Heading** », « ***### Heading »: bold wrapped around a heading line.
  out = out.replace(/^\*{2,3}[ \t]*(#{1,6} .*?)[ \t]*\*{0,3}[ \t]*$/gm, "$1");
  // A heading or list indented four spaces would read as code; lessons hold no code, so a
  // ```text fence (examples with **bold** in them) is unwrapped too.
  out = out.replace(/^[ \t]{4,}(?=#{1,6} |[-*] |\d+\. )/gm, "");
  out = out.replace(/^[ \t]*```[\w-]*[ \t]*$/gm, "");
  out = out.replace(/(?<=\|)[ \t]*\n(?:[ \t]*\n)+(?=[ \t]*\|)/g, "\n"); // gaps end a table
  out = out.replace(/&nbsp;/g, " ");
  return out.split("\n").map(splitTable).join("\n");
}
