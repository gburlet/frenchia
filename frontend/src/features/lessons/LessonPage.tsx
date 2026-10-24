import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router";
import { ArrowLeft, ArrowRight, CheckCircle2, Clock } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExerciseCard } from "@/features/exercises/ExerciseCard";
import { ApiError } from "@/lib/api/client";
import { useLesson, useUpdateProgress } from "./hooks";
import { SectionView } from "./sections";

function LessonSkeleton() {
  return (
    <div role="status" aria-label="Loading lesson" className="flex flex-col gap-4">
      <div className="h-6 w-16 animate-pulse rounded-full bg-surface" />
      <div className="h-10 w-2/3 animate-pulse rounded bg-surface" />
      <div className="h-5 w-1/3 animate-pulse rounded bg-surface" />
      <div className="h-64 animate-pulse rounded-card bg-surface" />
    </div>
  );
}

export function LessonPage() {
  const { lessonId = "" } = useParams();
  const lessonQuery = useLesson(lessonId);
  const progress = useUpdateProgress(lessonId);
  const markedRef = useRef<string | null>(null);
  const lesson = lessonQuery.data;
  const status = lesson?.progress.status;
  const { mutate } = progress;

  useEffect(() => {
    if (status === "not_started" && markedRef.current !== lessonId) {
      markedRef.current = lessonId;
      mutate({});
    }
  }, [status, lessonId, mutate]);

  if (lessonQuery.isPending) return <LessonSkeleton />;

  if (lessonQuery.isError) {
    const notFound = lessonQuery.error instanceof ApiError && lessonQuery.error.status === 404;
    if (notFound) {
      return (
        <div className="flex flex-col items-start gap-4">
          <h1 className="text-3xl">Lesson not found</h1>
          <p className="text-detail">This lesson isn’t published yet.</p>
          <Button asChild variant="secondary">
            <Link to="/curriculum">Back to the curriculum</Link>
          </Button>
        </div>
      );
    }
    return (
      <Alert>
        <AlertDescription>
          Couldn’t load this lesson: {lessonQuery.error.message}{" "}
          <button type="button" className="underline" onClick={() => void lessonQuery.refetch()}>
            Retry
          </button>
        </AlertDescription>
      </Alert>
    );
  }

  const completed = lesson!.progress.status === "completed";
  const l = lesson!;

  return (
    <article className="mx-auto flex max-w-3xl flex-col gap-10">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="teal">{l.level}</Badge>
          <Link to="/curriculum" className="text-sm text-teal underline">
            {l.unit.title}
          </Link>
        </div>
        <h1 lang="fr" className="text-3xl sm:text-4xl">{l.title}</h1>
        <p className="text-lg text-detail">{l.title_en}</p>
        <p className="flex items-center gap-1 text-sm text-muted">
          <Clock aria-hidden className="size-4" />
          About {l.estimated_minutes} min
        </p>
        {l.objectives.length > 0 && (
          <div>
            <h2 className="text-base">Objectives</h2>
            <ul className="mt-1 list-disc pl-5 text-sm text-detail">
              {l.objectives.map((o) => (
                <li key={o}>{o}</li>
              ))}
            </ul>
          </div>
        )}
      </header>

      {l.sections.map((section) => (
        <SectionView key={section.id} section={section} />
      ))}

      {l.exercises.length > 0 && (
        <section aria-labelledby="practice-heading" className="flex flex-col gap-4">
          <h2 id="practice-heading" className="text-2xl">Practice</h2>
          {l.exercises.map((ex, i) => (
            <ExerciseCard key={ex.exercise_revision_id} exercise={ex} number={i + 1} />
          ))}
        </section>
      )}

      <footer className="flex flex-col gap-6 border-t border-line pt-6">
        <div aria-live="polite">
          {completed ? (
            <p className="flex items-center gap-2 text-kept">
              <CheckCircle2 aria-hidden className="size-5" />
              Leçon terminée
            </p>
          ) : (
            <Button type="button" disabled={progress.isPending} onClick={() => progress.mutate({ completed: true })}>
              Marquer comme terminée
            </Button>
          )}
          {progress.isError && <p className="mt-2 text-sm text-error-text">Couldn’t save your progress.</p>}
        </div>
        <nav aria-label="Lesson navigation" className="flex flex-wrap justify-between gap-3">
          {l.previous ? (
            <Link to={`/lessons/${l.previous.id}`} className="flex items-center gap-2 text-teal hover:underline">
              <ArrowLeft aria-hidden className="size-4" />
              <span>
                <span className="block text-xs text-muted">Previous</span>
                {l.previous.title}
              </span>
            </Link>
          ) : (
            <span />
          )}
          {l.next && (
            <Link to={`/lessons/${l.next.id}`} className="flex items-center gap-2 text-right text-teal hover:underline">
              <span>
                <span className="block text-xs text-muted">Next</span>
                {l.next.title}
              </span>
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          )}
        </nav>
      </footer>
    </article>
  );
}
