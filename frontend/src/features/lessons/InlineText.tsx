import { Fragment } from "react";
import { inlineParts } from "@/lib/inline";

/** Short lesson text (examples, hints, options…) with its **bold** and *italic* rendered. */
export function InlineText({ text }: { text: string }) {
  return inlineParts(text).map((part, i) =>
    part.bold ? (
      <strong key={i} className="font-bold text-heading">
        {part.text}
      </strong>
    ) : part.italic ? (
      <em key={i} className="italic">
        {part.text}
      </em>
    ) : (
      <Fragment key={i}>{part.text}</Fragment>
    ),
  );
}
