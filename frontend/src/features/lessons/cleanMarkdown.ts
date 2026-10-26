// Generated lessons sometimes write line breaks as « <br> », « ⟩⟩⟩ » or « ⏎ » (and leave HTML
// comments); with raw HTML disabled these would show as text and flatten tables.
const LINE_BREAK = /<br\s*\/?>|⟩{2,}|⏎/gi;
const HTML_COMMENT = /<!--[\s\S]*?-->/g;

export function cleanMarkdown(text: string): string {
  return text.replace(HTML_COMMENT, "").replace(LINE_BREAK, "\n");
}
