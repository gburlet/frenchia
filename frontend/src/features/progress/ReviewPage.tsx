import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Loader2, Sparkles } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ExerciseCard } from "@/features/exercises/ExerciseCard";
import { ApiError } from "@/lib/api/client";
import type { ReviewItem, ReviewSet, WeakTopic } from "@/lib/api/progress";
import { progressKeys, useCompleteReview, useReview, useStartReview } from "./hooks";

type Outcome = ReviewItem["result"];

function Start({ weak }: { weak: WeakTopic[] }) {
  const start = useStartReview();
  return (
    <Card className="flex flex-col gap-4 p-5">
      {weak.length > 0 ? (
        <>
          <p className="text-detail">Your weakest topics right now:</p>
          <ul className="flex flex-col gap-2">
            {weak.map((t) => (
              <li key={t.id}>
                <span className="font-bold text-heading">{t.title}</span>{" "}
                <Badge variant="outline">{t.level}</Badge>
                <span className="block text-sm text-muted">{t.reason}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="text-detail">No weak spots yet: a review goes over the lessons you’ve started.</p>
      )}
      <Button className="self-start px-6 py-2.5" disabled={start.isPending} onClick={() => start.mutate()}>
        {start.isPending && <Loader2 aria-hidden className="size-4 animate-spin" />}
        Start a review
      </Button>
      {start.isError && (
        <p role="alert" className="text-sm text-error-text">
          {start.error instanceof ApiError ? start.error.detail : "Couldn’t start a review."}
        </p>
      )}
    </Card>
  );
}

function ExtrasStatus({ review }: { review: ReviewSet }) {
  if (review.extras === "queued" || review.extras === "running") {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-detail">
        <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
        The local AI is writing new exercises on your mistakes; they’ll be added at the end.
      </p>
    );
  }
  if (review.extras === "failed") {
    return <p className="text-sm text-muted">New exercises couldn’t be written this time; the review uses lesson exercises only.</p>;
  }
  return null;
}

function Summary({ review, outcomes }: { review: ReviewSet; outcomes: Outcome[] }) {
  const navigate = useNavigate();
  const complete = useCompleteReview();
  const right = outcomes.filter((o) => o === "correct" || o === "acceptable").length;
  return (
    <Card className="flex flex-col gap-4 p-5">
      <h2 className="text-2xl">Review done</h2>
      <p className="text-detail">
        {right} of {outcomes.length} right.{" "}
        {right < outcomes.length && "The topics you missed will come back in your next review."}
      </p>
      <ExtrasStatus review={review} />
      <div className="flex flex-wrap gap-3">
        <Button
          className="px-6 py-2.5"
          disabled={complete.isPending}
          onClick={() => complete.mutate(review.id, { onSuccess: () => void navigate("/") })}
        >
          Finish
        </Button>
      </div>
    </Card>
  );
}

function ItemHeader({ item, position, total }: { item: ReviewItem; position: number; total: number }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted tabular-nums">
        {position} / {total}
      </span>
      <Badge variant="teal">{item.topic.title}</Badge>
      {item.ai_generated ? (
        <Badge variant="outline" className="gap-1" title="Written by the local AI for you and checked automatically, not by a teacher">
          <Sparkles aria-hidden className="size-3" /> AI-generated
        </Badge>
      ) : (
        <span className="text-muted">{item.source_label}</span>
      )}
      <Link to={`/lessons/${item.lesson.id}`} className="ml-auto text-teal underline">
        {item.lesson.title}
      </Link>
    </div>
  );
}

function Session({ review }: { review: ReviewSet }) {
  const queryClient = useQueryClient();
  // Results from this visit; answers from an earlier visit come from the server.
  const [local, setLocal] = useState<Record<number, Outcome>>({});
  const outcomes = review.items.map((i) => local[i.exercise.exercise_revision_id] ?? i.result);
  const firstOpen = outcomes.findIndex((o) => o === null);
  const [index, setIndex] = useState(firstOpen === -1 ? review.items.length : firstOpen);
  const nextButton = useRef<HTMLButtonElement>(null);
  const item = review.items[index];
  const answered = item ? outcomes[index] !== null : false;

  useEffect(() => {
    if (answered) nextButton.current?.focus();
  }, [answered]);

  if (!item) return <Summary review={review} outcomes={outcomes} />;
  return (
    <div className="flex flex-col gap-4">
      <ItemHeader item={item} position={index + 1} total={review.items.length} />
      <ExerciseCard headingLevel={2}
        key={item.exercise.exercise_revision_id}
        exercise={item.exercise}
        lessonId={item.lesson.id}
        lessonTitle={item.lesson.title}
        autoActivate
        onResult={(result) => {
          setLocal((prev) => ({ ...prev, [item.exercise.exercise_revision_id]: result.verdict ?? "pending" }));
          void queryClient.invalidateQueries({ queryKey: progressKeys.dashboard });
        }}
      />
      <div className="flex items-center gap-3">
        {answered ? (
          <Button ref={nextButton} variant="secondary" onClick={() => setIndex(index + 1)}>
            {index + 1 < review.items.length ? "Next" : "See results"} <ArrowRight aria-hidden className="size-4" />
          </Button>
        ) : (
          <button type="button" className="cursor-pointer text-sm text-muted underline" onClick={() => setIndex(index + 1)}>
            Skip
          </button>
        )}
        <ExtrasStatus review={review} />
      </div>
    </div>
  );
}

export function ReviewPage() {
  const query = useReview();
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-3xl">Review</h1>
        <p className="text-detail">Practice on the topics you find hardest, picked from your answers.</p>
      </div>
      {query.isPending && <div role="status" aria-label="Loading your review" className="h-48 animate-pulse rounded-card bg-surface" />}
      {query.isError && (
        <Alert>
          <AlertDescription>Couldn’t load your review: {query.error.message}</AlertDescription>
        </Alert>
      )}
      {query.data &&
        (query.data.current ? (
          <Session key={query.data.current.id} review={query.data.current} />
        ) : (
          <Start weak={query.data.weak_topics} />
        ))}
    </div>
  );
}
