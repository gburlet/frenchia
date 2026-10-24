import { useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Curriculum, CurriculumLesson } from "@/lib/api/types";
import { findContinueLesson, useCurriculum } from "./hooks";
import { StatusPill } from "./StatusPill";

const DEFAULT_LEVEL = "A2";

function defaultLevel(curriculum: Curriculum): string {
  const found = findContinueLesson(curriculum);
  if (found?.inProgress) return found.level;
  return curriculum.levels.some((l) => l.level === DEFAULT_LEVEL)
    ? DEFAULT_LEVEL
    : (curriculum.levels[0]?.level ?? DEFAULT_LEVEL);
}

function LessonRow({ lesson }: { lesson: CurriculumLesson }) {
  const content = (
    <>
      <span className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
        <span className={cn("font-heading font-bold", lesson.published ? "text-heading" : "text-muted")}>
          {lesson.title}
        </span>
        <Badge variant="outline" className="w-fit capitalize">
          {lesson.kind}
        </Badge>
      </span>
      <StatusPill lesson={lesson} />
    </>
  );
  const base = "flex items-center justify-between gap-3 rounded-control border border-line px-4 py-3";
  if (!lesson.published) {
    return (
      <li>
        <div className={cn(base, "opacity-70")} aria-disabled="true">
          {content}
        </div>
      </li>
    );
  }
  return (
    <li>
      <Link to={`/lessons/${lesson.id}`} className={cn(base, "transition-colors hover:bg-white/5")}>
        {content}
      </Link>
    </li>
  );
}

export function CurriculumPage() {
  const query = useCurriculum();
  const [selected, setSelected] = useState<string | null>(null);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-4" role="status" aria-label="Loading curriculum">
        <div className="h-9 w-48 animate-pulse rounded bg-surface" />
        <div className="h-40 animate-pulse rounded-card bg-surface" />
      </div>
    );
  }
  if (query.isError) {
    return (
      <Alert>
        <AlertDescription>Couldn’t load the curriculum: {query.error.message}</AlertDescription>
      </Alert>
    );
  }

  const curriculum = query.data;
  const levelId = selected ?? defaultLevel(curriculum);
  const level = curriculum.levels.find((l) => l.level === levelId) ?? curriculum.levels[0];

  function onKeyDown(event: KeyboardEvent, index: number) {
    const count = curriculum.levels.length;
    let next: number;
    if (event.key === "ArrowRight") next = (index + 1) % count;
    else if (event.key === "ArrowLeft") next = (index - 1 + count) % count;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = count - 1;
    else return;
    event.preventDefault();
    const target = curriculum.levels[next]!.level;
    setSelected(target);
    tabRefs.current[target]?.focus();
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl">Curriculum</h1>
      <div role="tablist" aria-label="Levels" className="flex gap-2 overflow-x-auto">
        {curriculum.levels.map((l, i) => {
          const active = l.level === level?.level;
          return (
            <button
              key={l.level}
              ref={(el) => {
                tabRefs.current[l.level] = el;
              }}
              role="tab"
              id={`tab-${l.level}`}
              type="button"
              aria-selected={active}
              aria-controls={`panel-${l.level}`}
              tabIndex={active ? 0 : -1}
              onClick={() => setSelected(l.level)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={cn(
                "cursor-pointer rounded-full px-5 py-1.5 font-heading text-sm font-bold transition-colors",
                active ? "bg-purple text-heading" : "border border-line text-body hover:text-heading",
              )}
            >
              {l.level}
            </button>
          );
        })}
      </div>

      {level && (
        <section role="tabpanel" id={`panel-${level.level}`} aria-labelledby={`tab-${level.level}`} className="flex flex-col gap-6">
          <div>
            <h2 className="text-2xl">
              {level.level} · {level.title}
            </h2>
            <p className="mt-1 max-w-[70ch] text-detail">{level.summary}</p>
          </div>
          {level.units.length === 0 && <p className="text-detail">No units yet.</p>}
          {level.units.map((unit) => (
            <Card key={unit.id} aria-labelledby={`unit-${unit.id}`} role="region">
              <h3 id={`unit-${unit.id}`} className="text-xl">
                {unit.title}
              </h3>
              {unit.objectives.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-sm text-detail">
                  {unit.objectives.map((o) => (
                    <li key={o}>{o}</li>
                  ))}
                </ul>
              )}
              <ul className="mt-4 flex flex-col gap-2">
                {unit.lessons.map((lesson) => (
                  <LessonRow key={lesson.id} lesson={lesson} />
                ))}
              </ul>
            </Card>
          ))}
        </section>
      )}
    </div>
  );
}
