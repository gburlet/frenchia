import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { remarkLeftoverEmphasis } from "@/lib/remarkLeftoverEmphasis";
import { cn } from "@/lib/utils";
import { cleanMarkdown } from "./cleanMarkdown";

const components: Components = {
  h1: (p) => <h3 className="mt-4 mb-2 text-xl" {...p} />,
  h2: (p) => <h3 className="mt-4 mb-2 text-xl" {...p} />,
  h3: (p) => <h4 className="mt-3 mb-1 text-lg" {...p} />,
  h4: (p) => <h5 className="mt-3 mb-1 text-base" {...p} />,
  p: (p) => <p className="my-3 leading-relaxed" {...p} />,
  ul: (p) => <ul className="my-3 list-disc space-y-1 pl-6" {...p} />,
  ol: (p) => <ol className="my-3 list-decimal space-y-1 pl-6" {...p} />,
  strong: (p) => <strong className="font-bold text-heading" {...p} />,
  em: (p) => <em className="text-detail italic" {...p} />,
  a: (p) => <a className="text-teal underline hover:text-teal-hover" {...p} />,
  code: (p) => <code className="rounded bg-log px-1 py-0.5 text-sm" {...p} />,
  blockquote: (p) => <blockquote className="my-3 border-l-4 border-line pl-4 text-detail" {...p} />,
  table: (p) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm" {...p} />
    </div>
  ),
  th: (p) => <th className="border-b border-line px-3 py-2 text-heading" {...p} />,
  td: (p) => <td className="border-b border-line px-3 py-2" {...p} />,
};

/** Markdown (with GFM tables) and raw HTML disabled (react-markdown's default). */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("max-w-[70ch]", className)}>
      <ReactMarkdown components={components} remarkPlugins={[remarkGfm, remarkLeftoverEmphasis]}>
        {cleanMarkdown(children)}
      </ReactMarkdown>
    </div>
  );
}
