import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { VocabSetSummary } from "@/lib/api/vocab";
import { ProgressBar } from "./components";
import { useVocabSets } from "./hooks";

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-card bg-surface p-4">
      <dd className="text-2xl font-bold text-heading">{value}</dd>
      <dt className="text-sm text-detail">{label}</dt>
    </div>
  );
}

function SetCard({ set }: { set: VocabSetSummary }) {
  return (
    <li>
      <Link
        to={`/practice/vocab/sets/${set.slug}`}
        className="flex h-full flex-col gap-3 rounded-card bg-surface p-4 transition-colors hover:bg-chrome focus-visible:outline-2 focus-visible:outline-purple"
      >
        <div>
          <h3 className="text-lg text-heading">{set.title}</h3>
          <p className="text-sm text-detail">{set.title_en}</p>
        </div>
        <ProgressBar value={set.in_deck} max={set.size} label={`${set.title}: words in your deck`} />
        <p className="flex flex-wrap items-center gap-x-3 text-sm text-muted">
          <span>{set.size} words</span>
          <span>{set.in_deck}/{set.size} in deck</span>
          <span>{set.seen} seen</span>
          {set.due > 0 && <span className="font-bold text-warning-text">{set.due} due</span>}
        </p>
      </Link>
    </li>
  );
}

export function VocabPage() {
  const { data, isPending, isError, error } = useVocabSets();

  if (isPending) {
    return (
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <h1 className="text-3xl">Vocabulary Station</h1>
        <div role="status" aria-label="Loading vocabulary" className="h-48 animate-pulse rounded-card bg-surface" />
      </div>
    );
  }
  if (isError) {
    return (
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <h1 className="text-3xl">Vocabulary Station</h1>
        <Alert>
          <AlertDescription>Couldn’t load vocabulary: {error.message}</AlertDescription>
        </Alert>
      </div>
    );
  }

  const { sets, stats } = data;
  const waiting = stats.due_now + stats.new_remaining_today;
  const themes = sets.filter((s) => s.kind !== "lesson");
  const lessonSets = sets.filter((s) => s.kind === "lesson");
  const levels: string[] = [];
  for (const s of themes) if (!levels.includes(s.level)) levels.push(s.level);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8">
      <h1 className="text-3xl">Vocabulary Station</h1>

      <section aria-label="Your progress" className="flex flex-col gap-4">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Due now" value={stats.due_now} />
          <Stat label="New cards left today" value={stats.new_remaining_today} />
          <Stat label="Reviews today" value={stats.reviews_today} />
          <Stat label="Words in deck" value={stats.words} />
        </dl>
        <div className="flex flex-col items-start gap-2 rounded-card bg-surface p-5">
          {waiting > 0 ? (
            <>
              <p className="text-detail">
                <span className="text-xl font-bold text-heading">{waiting}</span> {waiting === 1 ? "card is" : "cards are"} waiting
              </p>
              <Button asChild>
                <Link to="/practice/vocab/review">Review now</Link>
              </Button>
            </>
          ) : (
            <>
              <p className="text-xl font-bold text-heading">All caught up</p>
              <p className="text-detail">
                {stats.words === 0 ? "Add a word set below to start reviewing." : "Nothing is due right now."}
              </p>
              <Button asChild variant="ghost">
                <Link to="/practice/vocab/review">Check for more</Link>
              </Button>
            </>
          )}
        </div>
      </section>

      {sets.length === 0 && (
        <div className="rounded-card bg-surface p-6">
          <h2 className="text-xl">No word sets yet</h2>
          <p className="text-detail">Vocabulary sets will appear here once they are available.</p>
        </div>
      )}

      {levels.map((level) => (
        <section key={level} aria-label={`Level ${level}`} className="flex flex-col gap-3">
          <h2 className="text-2xl">{level}</h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {themes
              .filter((s) => s.level === level)
              .map((s) => (
                <SetCard key={s.slug} set={s} />
              ))}
          </ul>
        </section>
      ))}

      {lessonSets.length > 0 && (
        <section aria-label="From your lessons" className="flex flex-col gap-3">
          <h2 className="text-2xl">From your lessons</h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {lessonSets.map((s) => (
              <SetCard key={s.slug} set={s} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
