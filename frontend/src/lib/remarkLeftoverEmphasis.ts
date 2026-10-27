import { inlineParts } from "./inline";

interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
}

/** Emphasis Markdown could not parse stays as literal asterisks in text nodes (« **qu'**il »:
 * a closing ** after an apostrophe and before a letter is not a valid delimiter). This turns
 * those leftovers into strong/emphasis nodes. */
export function remarkLeftoverEmphasis() {
  return (tree: MdNode) => {
    fix(tree);
  };
}

function fix(node: MdNode): void {
  if (!node.children) return;
  node.children = node.children.flatMap((child): MdNode[] => {
    if (child.type === "text" && child.value?.includes("*")) {
      return inlineParts(child.value).map((p) => {
        const text = { type: "text", value: p.text };
        if (p.bold) return { type: "strong", children: [text] };
        if (p.italic) return { type: "emphasis", children: [text] };
        return text;
      });
    }
    fix(child);
    return [child];
  });
}
