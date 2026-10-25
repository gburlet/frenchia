import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Lexeme, VocabStatus } from "@/lib/api/vocab";

export function GenderChip({ gender }: { gender: Lexeme["gender"] }) {
  if (!gender) return null;
  const masculine = gender === "m";
  return (
    <span
      title={masculine ? "Masculine" : "Feminine"}
      aria-label={masculine ? "masculine" : "feminine"}
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-bold",
        masculine ? "border-teal text-teal" : "border-purple bg-purple/20 text-heading",
      )}
    >
      {masculine ? "m." : "f."}
    </span>
  );
}

/** Region and formality badges (Québec usage, familiar register). */
export function UsageBadges({ lexeme }: { lexeme: Pick<Lexeme, "region" | "formality"> }) {
  return (
    <>
      {lexeme.region === "qc" && (
        <Badge variant="teal" title="Québec usage">
          QC
        </Badge>
      )}
      {lexeme.formality === "familiar" && (
        <Badge variant="warning" title="Familiar register">
          familiar
        </Badge>
      )}
    </>
  );
}

const STATUS: Record<VocabStatus, { label: string; variant: "outline" | "teal" | "warning" | "failure" }> = {
  not_started: { label: "Not started", variant: "outline" },
  new: { label: "New", variant: "teal" },
  learning: { label: "Learning", variant: "warning" },
  due: { label: "Due", variant: "failure" },
};

export function StatusPill({ status }: { status: VocabStatus }) {
  const s = STATUS[status];
  return <Badge variant={s.variant}>{s.label}</Badge>;
}

export function ProgressBar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      className="h-2 w-full overflow-hidden rounded-full bg-chrome"
    >
      <div className="h-full rounded-full bg-teal" style={{ width: `${pct}%` }} />
    </div>
  );
}
