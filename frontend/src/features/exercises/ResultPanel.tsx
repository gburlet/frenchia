import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SpeakButton } from "@/features/audio/SpeakButton";
import { useOpenTutor } from "@/components/layout/TutorDrawerContext";
import { cn } from "@/lib/utils";
import type { AttemptResult, PublicExercise, Verdict } from "@/lib/api/types";
import { useDispute, useRegrade } from "./hooks";
import { InlineText } from "@/features/lessons/InlineText";

const VERDICT: Record<Verdict | "pending", { label: string; variant: "success" | "teal" | "failure" | "blocked" }> = {
  correct: { label: "Correct", variant: "success" },
  acceptable: { label: "Acceptable", variant: "teal" },
  incorrect: { label: "Incorrect", variant: "failure" },
  pending: { label: "Pending", variant: "blocked" },
};

function HighlightedSpan({ text }: { text: string }) {
  return <span className="rounded-sm bg-failure/20 px-1 font-bold text-error-text">{text}</span>;
}

function DisputeControl({ attemptId }: { attemptId: number }) {
  const dispute = useDispute();
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");

  if (dispute.isSuccess) {
    return <p className="text-sm text-kept">Sent for review</p>;
  }
  if (!open) {
    return (
      <Button type="button" variant="ghost" className="h-8 px-3 text-xs" onClick={() => setOpen(true)}>
        I think I’m right
      </Button>
    );
  }
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        dispute.mutate({ attemptId, comment: comment.trim() || undefined });
      }}
    >
      <label htmlFor={`dispute-${attemptId}`} className="text-sm text-detail">
        Comment (optional)
      </label>
      <textarea
        id={`dispute-${attemptId}`}
        value={comment}
        onChange={(event) => setComment(event.target.value)}
        rows={2}
        className="w-full rounded-control border border-line bg-chrome p-2 text-sm text-heading"
      />
      <div className="flex items-center gap-3">
        <Button type="submit" variant="secondary" disabled={dispute.isPending}>
          Send for review
        </Button>
        {dispute.isError && <span className="text-sm text-error-text">Couldn’t send. Try again.</span>}
      </div>
    </form>
  );
}

interface ResultPanelProps {
  exercise: PublicExercise;
  result: AttemptResult;
  chosenIndex: number | null;
  onChange: (result: AttemptResult) => void;
  onRetry: () => void;
}

export function ResultPanel({ exercise, result, chosenIndex, onChange, onRetry }: ResultPanelProps) {
  const regrade = useRegrade();
  const openTutor = useOpenTutor();
  const pending = result.status === "pending" || result.grading === "pending" || result.verdict === null;
  const verdict = VERDICT[pending ? "pending" : result.verdict!];
  const { feedback } = result;
  const isChoice = exercise.type === "multiple_choice" || exercise.type === "comprehension";
  const frenchAnswer =
    exercise.type === "fill_blank" || (exercise.type === "translate" && exercise.direction === "en_fr");
  const answerText = feedback.corrected ?? result.correct_answer;
  const accepted = result.accepted_answers;
  const otherAccepted = accepted.filter((a) => a !== answerText);

  return (
    <div
      className={cn(
        "mt-4 flex flex-col gap-3 rounded-control border-l-4 bg-chrome p-4",
        verdict.variant === "success" && "border-success",
        verdict.variant === "teal" && "border-teal",
        verdict.variant === "failure" && "border-failure",
        verdict.variant === "blocked" && "border-blocked",
      )}
      data-testid="result-panel"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={verdict.variant}>{verdict.label}</Badge>
        {result.score !== null && <span className="text-xs text-muted">{result.score}/100</span>}
        {feedback.summary && <p className="text-heading">{feedback.summary}</p>}
      </div>

      {feedback.accent_only && (
        <p className="text-sm text-warning-text">Only the accents differ. Watch the accents (é, è, à, ç…).</p>
      )}

      {feedback.errors.length > 0 && (
        <ul className="flex flex-col gap-2" aria-label="Errors">
          {feedback.errors.map((error, i) => (
            <li key={i} className="text-sm">
              <Badge variant="outline" className="mr-2">
                {error.category}
              </Badge>
              {error.span && <HighlightedSpan text={error.span} />}
              {error.span && " "}
              <span className="text-detail"><InlineText text={error.explanation} /></span>
            </li>
          ))}
        </ul>
      )}

      {!pending && answerText && !isChoice && (
        <p className="flex flex-wrap items-center gap-1 text-heading">
          <span className="text-sm text-detail">{feedback.corrected ? "Corrected:" : "Answer:"}</span>
          <span className="font-bold">{answerText}</span>
          {frenchAnswer && <SpeakButton text={answerText} />}
        </p>
      )}

      {pending && (
        <div className="flex flex-col gap-2">
          {answerText && (
            <p className="text-sm text-detail">
              Reference answer: <span className="font-bold text-heading">{answerText}</span>
              {frenchAnswer && <SpeakButton text={answerText} />}
            </p>
          )}
          {otherAccepted.length > 0 && (
            <ul className="list-disc pl-5 text-sm text-detail">
              {otherAccepted.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
          <div className="flex items-center gap-3">
            <Button
              type="button"
              variant="secondary"
              disabled={regrade.isPending}
              onClick={() => regrade.mutate(result.attempt_id, { onSuccess: onChange })}
            >
              {regrade.isPending && <Loader2 aria-hidden className="size-4 animate-spin" />}
              Retry automatic feedback
            </Button>
            {regrade.isError && <span className="text-sm text-error-text">The tutor is still unavailable.</span>}
          </div>
        </div>
      )}

      {!pending && accepted.length === 1 && otherAccepted.length === 1 && (
        <p className="text-sm text-detail">Also accepted: {otherAccepted[0]}</p>
      )}
      {!pending && accepted.length > 1 && (
        <details className="text-sm text-detail">
          <summary className="cursor-pointer">Accepted answers ({accepted.length})</summary>
          <ul className="mt-1 list-disc pl-5">
            {accepted.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </details>
      )}

      {isChoice && !pending && (
        <ol className="flex flex-col gap-1" aria-label="Options">
          {exercise.options.map((option, i) => {
            const isCorrect = i === result.correct_index;
            const isChosen = i === chosenIndex;
            return (
              <li
                key={i}
                data-correct={isCorrect || undefined}
                className={cn(
                  "flex items-center gap-2 rounded-control border px-3 py-2 text-sm",
                  isCorrect ? "border-success bg-success/15 text-kept" : "border-line",
                  isChosen && !isCorrect && "border-failure bg-failure/15 text-error-text",
                )}
              >
                <span>{option}</span>
                {isCorrect && <Badge variant="success">Correct answer</Badge>}
                {isChosen && <Badge variant="outline">Your choice</Badge>}
              </li>
            );
          })}
        </ol>
      )}
      {result.explanation && (
        <p className="text-sm text-detail">
          <InlineText text={result.explanation} />
        </p>
      )}

      {feedback.register_note && <p className="text-sm text-muted">{feedback.register_note}</p>}

      <div className="flex flex-wrap items-center gap-3">
        {!pending && result.verdict === "incorrect" && (
          <Button type="button" variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        )}
        {!pending && !isChoice && result.verdict === "incorrect" && (
          <DisputeControl attemptId={result.attempt_id} />
        )}
        {!pending && (
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              openTutor({ prompt: result.verdict === "incorrect" ? "Why is my answer wrong?" : "Explain this point" })
            }
          >
            Ask the tutor about this
          </Button>
        )}
      </div>
      {result.grading === "llm" && <p className="text-xs text-muted">Feedback by the local AI tutor</p>}
    </div>
  );
}
