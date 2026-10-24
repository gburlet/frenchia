import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SpeakButton } from "@/features/audio/SpeakButton";
import { cn } from "@/lib/utils";
import type { AttemptResult, PublicExercise } from "@/lib/api/types";
import { useSubmitAttempt } from "./hooks";
import { ResultPanel } from "./ResultPanel";

interface ExerciseCardProps {
  exercise: PublicExercise;
  /** 1-based position shown in the heading (lessons). */
  number?: number;
  onResult?: (result: AttemptResult) => void;
  className?: string;
}

const typeLabel: Record<PublicExercise["type"], string> = {
  translate: "Translate",
  fill_blank: "Fill in the blank",
  multiple_choice: "Multiple choice",
  comprehension: "Comprehension",
};

const textareaClass =
  "w-full rounded-control border border-line bg-chrome p-3 text-base text-heading placeholder:text-muted focus-visible:border-purple disabled:cursor-not-allowed disabled:opacity-60";

export function ExerciseCard({ exercise, number, onResult, className }: ExerciseCardProps) {
  const uid = useId();
  const submit = useSubmitAttempt();
  const startedAt = useRef<number | null>(null);
  const [text, setText] = useState("");
  const [choice, setChoice] = useState<number | null>(null);
  const [showHint, setShowHint] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);

  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  const isChoice = exercise.type === "multiple_choice" || exercise.type === "comprehension";
  const waiting = submit.isPending;
  const locked = waiting || result !== null;
  const ready = isChoice ? choice !== null : text.trim().length > 0;

  function doSubmit() {
    if (!ready || locked) return;
    submit.mutate(
      {
        revisionId: exercise.exercise_revision_id,
        body: {
          answer: isChoice ? choice! : text.trim(),
          time_spent_ms: Date.now() - (startedAt.current ?? Date.now()),
        },
      },
      {
        onSuccess: (data) => {
          setResult(data);
          onResult?.(data);
        },
      },
    );
  }

  function reset() {
    submit.reset();
    setResult(null);
    setText("");
    setChoice(null);
    setShowHint(false);
    startedAt.current = Date.now();
  }

  function onTextKeyDown(event: KeyboardEvent) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      doSubmit();
    }
  }

  function onCardKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (!isChoice || locked) return;
    const target = event.target as HTMLElement;
    if (target.tagName === "TEXTAREA" || (target.tagName === "INPUT" && (target as HTMLInputElement).type === "text")) return;
    const n = Number(event.key);
    if (Number.isInteger(n) && n >= 1 && n <= Math.min(4, exercise.options.length)) {
      event.preventDefault();
      setChoice(n - 1);
      document.getElementById(`${uid}-opt-${n - 1}`)?.focus();
    } else if (event.key === "Enter") {
      event.preventDefault();
      doSubmit();
    }
  }

  const hint = "hint" in exercise ? exercise.hint : null;
  const headingId = `${uid}-title`;

  return (
    <Card
      className={cn("p-5", className)}
      onKeyDown={onCardKeyDown}
      role="group"
      aria-labelledby={headingId}
    >
      <h3 id={headingId} className="mb-3 flex items-baseline gap-2 text-base">
        {number !== undefined && <span className="text-teal">{number}.</span>}
        <span>{typeLabel[exercise.type]}</span>
      </h3>

      {exercise.type === "translate" && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-detail">
            {exercise.direction === "en_fr" ? "Translate into French" : "Translate into English"}
          </p>
          <p className="flex items-center gap-1 text-lg text-heading">
            <span lang={exercise.direction === "fr_en" ? "fr" : "en"}>{exercise.prompt}</span>
            {exercise.direction === "fr_en" && <SpeakButton text={exercise.prompt} />}
          </p>
          <label htmlFor={`${uid}-answer`} className="sr-only">
            Your translation
          </label>
          <textarea
            id={`${uid}-answer`}
            rows={3}
            value={text}
            disabled={locked}
            lang={exercise.direction === "en_fr" ? "fr" : "en"}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onTextKeyDown}
            placeholder="Type your answer (Enter to check, Shift+Enter for a new line)"
            className={textareaClass}
          />
        </div>
      )}

      {exercise.type === "fill_blank" && <FillBlank exercise={exercise} uid={uid} text={text} setText={setText} locked={locked} onKeyDown={onTextKeyDown} />}

      {isChoice && (
        <fieldset disabled={locked} className="flex flex-col gap-2 border-0 p-0">
          <legend className="mb-2 text-lg text-heading">
            {exercise.type === "comprehension" && (
              <a href={`#section-${exercise.reading_id}`} className="mb-1 block text-sm font-normal text-teal underline">
                About the reading
              </a>
            )}
            {exercise.question}
          </legend>
          <div role="radiogroup" aria-labelledby={headingId} className="flex flex-col gap-2">
            {exercise.options.map((option, i) => (
              <label
                key={i}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-control border border-line px-3 py-2 text-heading has-[:checked]:border-purple has-[:checked]:bg-purple/15 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-purple",
                  locked && "cursor-default opacity-80",
                )}
              >
                <input
                  id={`${uid}-opt-${i}`}
                  type="radio"
                  name={`${uid}-choice`}
                  checked={choice === i}
                  onChange={() => setChoice(i)}
                  className="accent-purple"
                />
                {i < 4 && <kbd className="text-xs text-muted">{i + 1}</kbd>}
                <span>{option}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      {hint && !result && (
        <div className="mt-3">
          {exercise.type === "fill_blank" ? (
            <p className="text-sm text-detail">Hint: {hint}</p>
          ) : (
            <>
              <button
                type="button"
                aria-expanded={showHint}
                onClick={() => setShowHint((v) => !v)}
                className="cursor-pointer text-sm text-teal underline"
              >
                {showHint ? "Hide hint" : "Show hint"}
              </button>
              {showHint && <p className="mt-1 text-sm text-detail">{hint}</p>}
            </>
          )}
        </div>
      )}

      {!result && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button type="button" onClick={doSubmit} disabled={!ready || locked} className="px-6 py-2.5">
            Check
          </Button>
          {waiting && exercise.type === "translate" && (
            <p role="status" className="flex items-center gap-2 text-sm text-detail">
              <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
              Checking your answer…
            </p>
          )}
          {submit.isError && (
            <p role="alert" className="text-sm text-error-text">
              Couldn’t check your answer: {submit.error.message}
            </p>
          )}
        </div>
      )}

      <div aria-live="polite">
        {result && (
          <ResultPanel
            exercise={exercise}
            result={result}
            chosenIndex={choice}
            onChange={(next) => {
              setResult(next);
              onResult?.(next);
            }}
            onRetry={reset}
          />
        )}
      </div>
    </Card>
  );
}

function FillBlank({
  exercise,
  uid,
  text,
  setText,
  locked,
  onKeyDown,
}: {
  exercise: Extract<PublicExercise, { type: "fill_blank" }>;
  uid: string;
  text: string;
  setText: (v: string) => void;
  locked: boolean;
  onKeyDown: (e: KeyboardEvent) => void;
}) {
  const [before, ...rest] = exercise.sentence.split("___");
  const after = rest.join("___");
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-detail">Fill in the blank</p>
      <p lang="fr" className="flex flex-wrap items-center gap-x-2 gap-y-2 text-lg text-heading">
        <span>{before}</span>
        <input
          type="text"
          aria-label="Missing word"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          value={text}
          disabled={locked}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          id={`${uid}-answer`}
          className="h-9 w-40 rounded-control border border-line bg-chrome px-2 text-base text-heading focus-visible:border-purple disabled:opacity-60"
        />
        <span>{after}</span>
        <SpeakButton text={exercise.sentence.replace("___", "…")} label="Écouter la phrase" />
      </p>
      {exercise.translation_en && <p className="text-sm text-muted">{exercise.translation_en}</p>}
    </div>
  );
}
