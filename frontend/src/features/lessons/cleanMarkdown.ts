// Generated lessons sometimes write line breaks as « <br> », « ⟩⟩⟩ » or « ⏎ » (and leave HTML
// comments); with raw HTML disabled these would show as text and flatten tables.
const LINE_BREAK = /<br\s*\/?>|⟩{2,}|⏎/gi;
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
  return out.split("\n").map(splitTable).join("\n");
}
