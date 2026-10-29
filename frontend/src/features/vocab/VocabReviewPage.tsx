import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AccentKeys } from "@/components/AccentKeys";
import { SpeakButton } from "@/features/audio/SpeakButton";
import {
  checkVocabCard,
  fetchVocabReview,
  removeVocabWord,
  reviewVocabCard,
  type CheckResponse,
  type Rating,
  type ReviewCard,
} from "@/lib/api/vocab";
import { cn } from "@/lib/utils";
import { GenderChip, UsageBadges } from "./components";
import { formatInterval } from "./format";
import { useVocabSets, vocabKeys } from "./hooks";
import { InlineText } from "@/features/lessons/InlineText";

const RATINGS: { value: Rating; label: string }[] = [
  { value: 1, label: "Again" },
  { value: 2, label: "Hard" },
  { value: 3, label: "Good" },
  { value: 4, label: "Easy" },
];

const RESULT_STYLE: Record<CheckResponse["result"], { label: string; border: string; variant: "success" | "teal" | "warning" | "failure" }> = {
  correct: { label: "Correct", border: "border-success", variant: "success" },
  accent: { label: "Accent", border: "border-teal", variant: "teal" },
  article: { label: "Article", border: "border-blocked", variant: "warning" },
  gender: { label: "Gender", border: "border-blocked", variant: "warning" },
  incorrect: { label: "Incorrect", border: "border-failure", variant: "failure" },
};

const LEARN_AHEAD_MS = 20 * 60 * 1000;

function isTyping(target: EventTarget | null) {
  const t = target as HTMLElement | null;
  return !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT");
}

interface CardProps {
  card: ReviewCard;
  onRated: (rating: Rating) => void;
  onRemoved: () => void;
}

function Example({ card }: { card: ReviewCard }) {
  const { lexeme } = card;
  return (
    <>
      {lexeme.example_fr && (
        <p className="flex flex-wrap items-center gap-1 text-sm">
          <span lang="fr" className="text-heading">{lexeme.example_fr}</span>
          <SpeakButton text={lexeme.example_fr} className="size-7" />
          {lexeme.example_en && <span className="basis-full text-muted"><InlineText text={lexeme.example_en} /></span>}
        </p>
      )}
      {lexeme.note && <p className="text-sm text-muted"><InlineText text={lexeme.note} /></p>}
    </>
  );
}

function ReviewCardView({ card, onRated, onRemoved }: CardProps) {
  const { lexeme } = card;
  const recall = card.direction === "recall";
  const [shownAt] = useState(() => Date.now());
  const inputRef = useRef<HTMLInputElement | null>(null);
  const lock = useRef(false);
  const [revealed, setRevealed] = useState(false);
  const [answer, setAnswer] = useState("");
  const [checked, setChecked] = useState<CheckResponse | null>(null);
  const [selected, setSelected] = useState<Rating | null>(null);

  const check = useMutation({
    mutationFn: () => checkVocabCard(card.id, answer.trim()),
    onSuccess: (res) => {
      setChecked(res);
      setSelected(res.suggested_rating);
      inputRef.current?.blur();
    },
  });
  const rate = useMutation({
    mutationFn: (rating: Rating) =>
      reviewVocabCard(card.id, {
        rating,
        duration_ms: Date.now() - shownAt,
        ...(recall && checked ? { answer: answer.trim(), check_result: checked.result } : {}),
      }),
    onSuccess: (_d, rating) => onRated(rating),
    onSettled: () => {
      lock.current = false;
    },
  });

  const remove = useMutation({
    mutationFn: () => removeVocabWord(card.id),
    onSuccess: () => onRemoved(),
    onSettled: () => {
      lock.current = false;
    },
  });

  const ready = recall ? checked !== null : revealed;

  function submitRating(rating: Rating) {
    if (!ready || lock.current) return;
    lock.current = true;
    rate.mutate(rating);
  }

  // Latest-handler ref so the window listener never goes stale.
  const handler = useRef<(e: KeyboardEvent) => void>(() => {});
  const nextHandler = (event: KeyboardEvent) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const onButton = (event.target as HTMLElement | null)?.tagName === "BUTTON";
    if (!ready) {
      if (!recall && !onButton && (event.key === " " || event.key === "Enter") && !isTyping(event.target)) {
        event.preventDefault();
        setRevealed(true);
      }
      return;
    }
    if (isTyping(event.target) && !checked) return;
    if (event.key >= "1" && event.key <= "4") {
      event.preventDefault();
      submitRating(Number(event.key) as Rating);
    } else if (event.key === "Enter" && !onButton && selected) {
      event.preventDefault();
      submitRating(selected);
    }
  };
  useEffect(() => {
    handler.current = nextHandler;
  });
  useEffect(() => {
    const fn = (e: KeyboardEvent) => handler.current(e);
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, []);

  useEffect(() => {
    if (recall) inputRef.current?.focus();
  }, [recall]);

  const style = checked ? RESULT_STYLE[checked.result] : null;

  return (
    <div className="flex flex-col gap-5 rounded-card bg-surface p-5 sm:p-8">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{recall ? "English → French" : "French → English"}</Badge>
        {card.is_new && <Badge variant="teal">New</Badge>}
        {(!recall || ready) && (
          <>
            <UsageBadges lexeme={lexeme} />
          </>
        )}
        <Button
          type="button"
          variant="ghost"
          className="ml-auto"
          title="Stop reviewing this word, in both directions"
          disabled={remove.isPending || rate.isPending}
          onClick={() => {
            if (lock.current) return;
            lock.current = true;
            remove.mutate();
          }}
        >
          Remove this word
        </Button>
      </div>

      {recall ? (
        <>
          <div>
            <p className="text-3xl font-bold text-heading">{lexeme.en}</p>
            <p className="text-sm text-detail">{lexeme.pos}</p>
          </div>
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (!checked && answer.trim() && !check.isPending) check.mutate();
            }}
          >
            <label htmlFor="vocab-answer" className="text-sm text-detail">
              Your French answer
            </label>
            <input
              id="vocab-answer"
              ref={inputRef}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              readOnly={!!checked}
              lang="fr"
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              className="h-12 w-full rounded-control border border-line bg-chrome px-3 text-lg text-heading focus-visible:border-purple focus-visible:outline-purple"
            />
            {!checked && (
              <>
                <AccentKeys target={inputRef} onInsert={setAnswer} />
                <div>
                  <Button type="submit" variant="secondary" disabled={!answer.trim() || check.isPending}>
                    Check
                  </Button>
                </div>
              </>
            )}
            {check.isError && <p className="text-sm text-error-text">Couldn’t check: {check.error.message}</p>}
          </form>
          <div aria-live="polite">
            {checked && style && (
              <div className={cn("flex flex-col gap-2 rounded-control border-l-4 bg-chrome p-4", style.border)} data-testid="check-result">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={style.variant}>{style.label}</Badge>
                  <span className="text-sm text-detail">Answer:</span>
                  <span lang="fr" className="text-xl font-bold text-heading">{checked.expected}</span>
                  <SpeakButton text={checked.expected} />
                  <GenderChip gender={lexeme.gender} />
                </div>
                {checked.message && <p className="text-detail">{checked.message}</p>}
                <Example card={card} />
              </div>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <p lang="fr" className="text-4xl font-bold text-heading">{lexeme.display}</p>
            <SpeakButton text={lexeme.display} />
          </div>
          <div aria-live="polite">
            {revealed ? (
              <div className="flex flex-col gap-2 rounded-control border-l-4 border-teal bg-chrome p-4">
                <p className="flex flex-wrap items-center gap-2 text-2xl text-heading">
                  {lexeme.en} <GenderChip gender={lexeme.gender} />
                  <span className="text-sm text-detail">{lexeme.pos}</span>
                </p>
                <Example card={card} />
              </div>
            ) : (
              <Button type="button" variant="secondary" onClick={() => setRevealed(true)}>
                Show answer <kbd className="text-xs opacity-70">Space</kbd>
              </Button>
            )}
          </div>
        </>
      )}

      {ready && (
        <div role="group" aria-label="Rate your recall" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {RATINGS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              disabled={rate.isPending}
              aria-pressed={selected === value}
              onClick={() => submitRating(value)}
              className={cn(
                "flex min-h-14 cursor-pointer flex-col items-center justify-center rounded-control border bg-chrome px-2 py-2 text-heading transition-colors hover:border-teal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple disabled:opacity-60",
                selected === value ? "border-purple ring-2 ring-purple" : "border-line",
              )}
            >
              <span className="font-bold">
                {label} <kbd className="text-xs font-normal opacity-70">{value}</kbd>
              </span>
              <span className="text-xs text-detail">{formatInterval(card.previews[String(value) as "1"])}</span>
            </button>
          ))}
        </div>
      )}
      {rate.isError && <p className="text-sm text-error-text">Couldn’t save your rating: {rate.error.message}. Try again.</p>}
      {remove.isError && <p className="text-sm text-error-text">Couldn’t remove the word: {remove.error.message}</p>}
    </div>
  );
}

export function VocabReviewPage() {
  const [batch, setBatch] = useState(0);
  const [ahead, setAhead] = useState(false);
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState(0);
  const [again, setAgain] = useState(0);
  // Words removed this session; the batch may still hold their other direction.
  const [removed, setRemoved] = useState<ReadonlySet<number>>(new Set());
  const [lastRemoved, setLastRemoved] = useState<ReviewCard | null>(null);

  const query = useQuery({
    queryKey: vocabKeys.review(batch, ahead),
    queryFn: ({ signal }) => fetchVocabReview(ahead, signal),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const data = query.data;
  const empty = !!data && data.cards.length === 0;
  const sets = useVocabSets(empty);

  const undo = useMutation({
    mutationFn: (card: ReviewCard) => removeVocabWord(card.id, false),
    onSuccess: (_d, card) => {
      setRemoved((prev) => new Set([...prev].filter((id) => id !== card.lexeme.id)));
      setLastRemoved(null);
      if (empty) {
        setIndex(0);
        setBatch((b) => b + 1);
      }
    },
  });

  function advance(skip: ReadonlySet<number>) {
    if (!data) return;
    let next = index + 1;
    while (next < data.cards.length && skip.has(data.cards[next]?.lexeme.id ?? -1)) next++;
    if (next >= data.cards.length) {
      setIndex(0);
      setBatch((b) => b + 1);
    } else {
      setIndex(next);
    }
  }

  function onRated(rating: Rating) {
    setDone((d) => d + 1);
    if (rating === 1) setAgain((a) => a + 1);
    advance(removed);
  }

  function onRemoved(card: ReviewCard) {
    const skip = new Set(removed).add(card.lexeme.id);
    setRemoved(skip);
    setLastRemoved(card);
    undo.reset();
    advance(skip);
  }

  const notice = lastRemoved && (
    <div className="flex flex-wrap items-center gap-3 rounded-card bg-surface px-4 py-3 text-detail" role="status">
      <span>
        Removed <span lang="fr" className="font-bold text-heading">{lastRemoved.lexeme.display}</span> from your reviews.
      </span>
      <Button type="button" variant="ghost" disabled={undo.isPending} onClick={() => undo.mutate(lastRemoved)}>
        Undo
      </Button>
      {undo.isError && <span className="text-error-text">Couldn’t undo: {undo.error.message}</span>}
    </div>
  );

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h1 className="text-3xl">Vocabulary review</h1>
      <Link to="/practice/vocab" className="text-sm text-teal underline">Back to the station</Link>
    </div>
  );

  if (query.isError) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        {header}
        <Alert>
          <AlertDescription>Couldn’t load your reviews: {query.error.message}</AlertDescription>
        </Alert>
        <div>
          <Button type="button" variant="secondary" onClick={() => void query.refetch()}>Try again</Button>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        {header}
        <div role="status" aria-label="Loading cards" className="h-64 animate-pulse rounded-card bg-surface" />
      </div>
    );
  }

  if (empty) {
    const nextMs = data.next_due ? Date.parse(data.next_due) - query.dataUpdatedAt : null;
    const soon = nextMs !== null && nextMs <= LEARN_AHEAD_MS && !ahead;
    const limitReached = data.new_remaining_today === 0 && (sets.data?.stats.new_waiting ?? 0) > 0;
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        {header}
        {notice}
        <div className="flex flex-col items-start gap-3 rounded-card bg-surface p-6">
          <h2 className="text-2xl">All caught up</h2>
          <p className="text-detail">
            This session: {done} {done === 1 ? "card" : "cards"} reviewed{done > 0 ? `, ${again} to repeat` : ""}.
          </p>
          {sets.data?.stats.words === 0 && (
            <p className="text-detail">
              Your deck is empty. Open a word set at the{" "}
              <Link to="/practice/vocab" className="text-teal underline">Vocabulary Station</Link> and add its words to your reviews.
            </p>
          )}
          {limitReached && (
            <p className="text-detail">You’ve reached today’s limit of new cards. More will be available tomorrow.</p>
          )}
          {soon && (
            <>
              <p className="text-detail">Another card is due soon.</p>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setAhead(true);
                  setBatch((b) => b + 1);
                  setIndex(0);
                }}
              >
                Learn ahead
              </Button>
            </>
          )}
          <Button asChild variant="ghost">
            <Link to="/practice/vocab">Back to the station</Link>
          </Button>
        </div>
      </div>
    );
  }

  const card = data.cards[index];
  if (!card) return null;
  const left = data.cards.slice(index).filter((c) => !removed.has(c.lexeme.id)).length;
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      {header}
      {notice}
      <p className="text-sm text-detail" aria-live="polite">
        Done this session: {done} · {left} left in this batch · {data.due_count} due
      </p>
      <ReviewCardView key={`${batch}-${card.id}`} card={card} onRated={onRated} onRemoved={() => onRemoved(card)} />
    </div>
  );
}
