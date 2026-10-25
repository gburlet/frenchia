import { Link, useParams } from "react-router";
import { Check, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SpeakButton } from "@/features/audio/SpeakButton";
import { ApiError } from "@/lib/api/client";
import type { Lexeme, VocabStatus } from "@/lib/api/vocab";
import { GenderChip, StatusPill, UsageBadges } from "./components";
import { useLearnSet, useVocabSet } from "./hooks";

function WordRow({ word }: { word: Lexeme & { status: VocabStatus } }) {
  return (
    <li className="flex flex-col gap-2 rounded-card bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span lang="fr" className="text-2xl font-bold text-heading">{word.display}</span>
        <SpeakButton text={word.display} />
        <GenderChip gender={word.gender} />
        <UsageBadges lexeme={word} />
        <Badge variant="outline">{word.pos}</Badge>
        <span className="ml-auto">
          <StatusPill status={word.status} />
        </span>
      </div>
      <p className="text-detail">
        {word.en}
        {word.plural && (
          <span className="text-muted">
            {" "}
            · plural: <span lang="fr">{word.plural}</span>
          </span>
        )}
      </p>
      {word.example_fr && (
        <p className="flex flex-wrap items-center gap-1 text-sm">
          <span lang="fr" className="text-heading">{word.example_fr}</span>
          <SpeakButton text={word.example_fr} className="size-7" />
          {word.example_en && <span className="basis-full text-muted">{word.example_en}</span>}
        </p>
      )}
      {word.note && <p className="text-sm text-muted">{word.note}</p>}
    </li>
  );
}

export function VocabSetPage() {
  const { slug = "" } = useParams();
  const { data, isPending, isError, error } = useVocabSet(slug);
  const learn = useLearnSet(slug);

  if (isPending) {
    return <div role="status" aria-label="Loading word set" className="mx-auto h-48 max-w-3xl animate-pulse rounded-card bg-surface" />;
  }
  if (isError) {
    const missing = error instanceof ApiError && error.status === 404;
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        <Alert>
          <AlertDescription>{missing ? "This word set doesn’t exist." : `Couldn’t load the set: ${error.message}`}</AlertDescription>
        </Alert>
        <Link to="/practice/vocab" className="text-teal underline">Back to the Vocabulary Station</Link>
      </div>
    );
  }

  const allIn = data.words.length > 0 && data.words.every((w) => w.status !== "not_started");

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <Link to="/practice/vocab" className="text-sm text-teal underline">Vocabulary Station</Link>
        <h1 className="mt-1 text-3xl">{data.title}</h1>
        <p className="flex items-center gap-2 text-detail">
          <Badge variant="outline">{data.level}</Badge> {data.title_en} · {data.words.length} words
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {allIn ? (
          <span className="inline-flex items-center gap-2 font-bold text-kept">
            <Check aria-hidden className="size-5" /> In your reviews
          </span>
        ) : (
          <Button type="button" disabled={learn.isPending} onClick={() => learn.mutate()}>
            {learn.isPending && <Loader2 aria-hidden className="size-4 animate-spin" />}
            Add these words to my reviews
          </Button>
        )}
        <Button asChild variant="secondary">
          <Link to="/practice/vocab/review">Review now</Link>
        </Button>
      </div>
      <div aria-live="polite">
        {learn.isSuccess && (
          <p className="text-kept">
            Added {learn.data.added} {learn.data.added === 1 ? "word" : "words"} ({learn.data.skipped} already in your deck)
          </p>
        )}
        {learn.isError && <p className="text-error-text">Couldn’t add the words: {learn.error.message}</p>}
      </div>

      <ul className="flex flex-col gap-3" aria-label="Words">
        {data.words.map((w) => (
          <WordRow key={w.id} word={w} />
        ))}
      </ul>
    </div>
  );
}
