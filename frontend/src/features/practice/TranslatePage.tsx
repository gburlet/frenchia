import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ExerciseCard } from "@/features/exercises/ExerciseCard";
import { ApiError } from "@/lib/api/client";
import { fetchTranslateNext, fetchTranslateOptions } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import type { TranslateFilters } from "@/lib/api/types";

const selectClass =
  "h-11 w-full rounded-control border border-line bg-chrome px-3 text-base text-heading focus-visible:border-purple";

export function TranslatePage() {
  const [params, setParams] = useSearchParams();
  const filters: TranslateFilters = {
    level: params.get("level") || undefined,
    topic: params.get("topic") || undefined,
    direction: params.get("direction") || undefined,
  };
  const [answered, setAnswered] = useState(false);

  const options = useQuery({
    queryKey: queryKeys.translateOptions,
    queryFn: ({ signal }) => fetchTranslateOptions(signal),
    staleTime: 60_000,
  });
  const next = useQuery({
    queryKey: queryKeys.translateNext(filters),
    queryFn: ({ signal }) => fetchTranslateNext(filters, signal),
    retry: false,
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  function setFilter(key: keyof TranslateFilters, value: string) {
    const copy = new URLSearchParams(params);
    if (value) copy.set(key, value);
    else copy.delete(key);
    if (key === "level") copy.delete("topic");
    setAnswered(false);
    setParams(copy, { replace: true });
  }

  const { refetch } = next;
  function loadNext() {
    setAnswered(false);
    void refetch();
  }

  useEffect(() => {
    if (!answered) return;
    function onKey(event: KeyboardEvent) {
      const t = event.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
      if (event.key === "n" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault();
        setAnswered(false);
        void refetch();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [answered, refetch]);

  const topics = (options.data?.topics ?? []).filter((t) => !filters.level || t.level === filters.level);
  const empty = next.error instanceof ApiError && next.error.status === 404;
  const loading = next.isPending || (next.isFetching && !next.isError && answered === false && !next.data);
  const exercise = next.data;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <h1 className="text-3xl">Translation Station</h1>

      <form className="grid gap-4 sm:grid-cols-3" aria-label="Filters" onSubmit={(e) => e.preventDefault()}>
        <div>
          <label htmlFor="f-level" className="mb-1 block text-sm text-detail">Level</label>
          <select id="f-level" className={selectClass} value={filters.level ?? ""} onChange={(e) => setFilter("level", e.target.value)}>
            <option value="">All levels</option>
            {(options.data?.levels ?? []).map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="f-topic" className="mb-1 block text-sm text-detail">Grammar topic</label>
          <select id="f-topic" className={selectClass} value={filters.topic ?? ""} onChange={(e) => setFilter("topic", e.target.value)}>
            <option value="">All topics</option>
            {topics.map((t) => (
              <option key={t.id} value={t.id}>{`${t.title} (${t.count})`}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="f-direction" className="mb-1 block text-sm text-detail">Direction</label>
          <select id="f-direction" className={selectClass} value={filters.direction ?? ""} onChange={(e) => setFilter("direction", e.target.value)}>
            <option value="">Both directions</option>
            <option value="en_fr">EN → FR</option>
            <option value="fr_en">FR → EN</option>
          </select>
        </div>
      </form>

      {loading && (
        <div role="status" aria-label="Loading exercise" className="h-48 animate-pulse rounded-card bg-surface" />
      )}

      {empty && (
        <div className="flex flex-col items-start gap-3 rounded-card bg-surface p-6">
          <h2 className="text-xl">No translation exercises match yet</h2>
          <p className="text-detail">Try different filters, or work through a lesson to unlock more.</p>
          <Button asChild variant="secondary">
            <Link to="/curriculum">Browse the curriculum</Link>
          </Button>
        </div>
      )}

      {next.isError && !empty && (
        <Alert>
          <AlertDescription>Couldn’t load an exercise: {next.error.message}</AlertDescription>
        </Alert>
      )}

      {exercise && !(next.isFetching && answered === false && next.isRefetching) && (
        <>
          <ExerciseCard
            key={`${exercise.exercise_revision_id}-${next.dataUpdatedAt}`}
            exercise={exercise}
            onResult={() => setAnswered(true)}
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted">
              From lesson{" "}
              <Link to={`/lessons/${exercise.lesson.id}`} className="text-teal underline">
                {exercise.lesson.title}
              </Link>
            </p>
            {answered && (
              <Button type="button" onClick={loadNext}>
                Next <kbd className="ml-1 text-xs opacity-70">n</kbd>
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
