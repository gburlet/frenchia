import { Link, useParams } from "react-router";
import { Check, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SpeakButton } from "@/features/audio/SpeakButton";
import { ApiError } from "@/lib/api/client";
import type { Lexeme, VocabStatus } from "@/lib/api/vocab";
import { GenderChip, StatusPill, UsageBadges } from "./components";
import { useLearnSet, useRemoveSet, useVocabSet, useWordInDeck } from "./hooks";
import { InlineText } from "@/features/lessons/InlineText";

const OWN: VocabStatus[] = ["new", "learning", "due"];

function WordRow({ word }: { word: Lexeme & { status: VocabStatus } }) {
  const inDeck = OWN.includes(word.status);
  const toggle = useWordInDeck(word.id, inDeck);
  return (
    <li className="flex flex-col gap-2 rounded-card bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span lang="fr" className="text-2xl font-bold text-heading">{word.display}</span>
        <SpeakButton text={word.display} />
        <GenderChip gender={word.gender} />
        <UsageBadges lexeme={word} />
        <Badge variant="outline">{word.pos}</Badge>
        <span className="ml-auto flex items-center gap-2">
          <StatusPill status={word.status} />
          {word.status !== "elsewhere" && (
            <Button
              type="button"
              variant="pill"
              className={inDeck ? "border border-solid border-line bg-transparent text-body" : undefined}
              disabled={toggle.isPending}
              aria-label={`${inDeck ? "Remove from deck" : "Add to deck"}: ${word.display}`}
              onClick={() => toggle.mutate()}
            >
              {toggle.isPending && <Loader2 aria-hidden className="size-3 animate-spin" />}
              {inDeck ? "Remove from deck" : "Add to deck"}
            </Button>
          )}
        </span>
      </div>
      {toggle.isError && <p className="text-sm text-error-text">Couldn’t update your deck: {toggle.error.message}</p>}
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
          {word.example_en && <span className="basis-full text-muted"><InlineText text={word.example_en} /></span>}
        </p>
      )}
      {word.note && <p className="text-sm text-muted"><InlineText text={word.note} /></p>}
    </li>
  );
}

export function VocabSetPage() {
  const { slug = "" } = useParams();
  const { data, isPending, isError, error } = useVocabSet(slug);
  const learn = useLearnSet(slug);
  const remove = useRemoveSet(slug);
  const busy = learn.isPending || remove.isPending;

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

  const inDeck = data.words.filter((w) => OWN.includes(w.status)).length;
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
          <Button
            type="button"
            variant={inDeck > 0 ? "secondary" : "primary"}
            disabled={busy}
            onClick={() => {
              remove.reset();
              learn.mutate();
            }}
          >
            {learn.isPending && <Loader2 aria-hidden className="size-4 animate-spin" />}
            Add these words to my reviews
          </Button>
        )}
        {inDeck > 0 && (
          <>
            <Button asChild variant="secondary">
              <Link to="/practice/vocab/review">Review now</Link>
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                learn.reset();
                remove.mutate();
              }}
            >
              {remove.isPending && <Loader2 aria-hidden className="size-4 animate-spin" />}
              Remove from my reviews
            </Button>
          </>
        )}
      </div>
      <p className="text-sm text-detail">
        {inDeck > 0
          ? "These words are mixed into your daily reviews with your other sets. New words are introduced a few each day. Removing the set keeps your progress for later."
          : "Adding the set puts its words in your review deck. Your daily reviews then introduce them a few at a time, French → English first, then English → French."}
      </p>
      <div aria-live="polite">
        {learn.isSuccess && (
          <p className="text-kept">
            Added {learn.data.added} {learn.data.added === 1 ? "word" : "words"} ({learn.data.skipped} already in your deck)
          </p>
        )}
        {learn.isError && <p className="text-error-text">Couldn’t add the words: {learn.error.message}</p>}
        {remove.isSuccess && (
          <p className="text-detail">
            Removed {remove.data.removed} {remove.data.removed === 1 ? "word" : "words"} from your reviews. Your
            progress is kept if you add the set again.
          </p>
        )}
        {remove.isError && <p className="text-error-text">Couldn’t remove the words: {remove.error.message}</p>}
      </div>

      <ul className="flex flex-col gap-3" aria-label="Words">
        {data.words.map((w) => (
          <WordRow key={w.id} word={w} />
        ))}
      </ul>
    </div>
  );
}
