/** Lesson text is plain apart from **bold**, which marks the form being taught. */
export function BoldText({ text }: { text: string }) {
  return text.split(/\*\*(.+?)\*\*/g).map((part, i) =>
    i % 2 ? (
      <strong key={i} className="font-bold text-heading">
        {part}
      </strong>
    ) : (
      part
    ),
  );
}
