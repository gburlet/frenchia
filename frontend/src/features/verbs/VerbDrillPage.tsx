import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AccentKeys } from "@/components/AccentKeys";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SpeakButton } from "@/features/audio/SpeakButton";
import { createDrill, submitVerbAnswers } from "@/lib/api/verbs";
import type { DrillItem, DrillMode, DrillRequest, VerbAnswerResult } from "@/lib/api/verbs";
import { cn } from "@/lib/utils";
import { apiErrorMessage, diffMask, drillUrl } from "./utils";

interface Entry {
  item: DrillItem;
  answer: string;
  result: VerbAnswerResult;
}

const FEEDBACK = {
  correct: { title: "Correct!", cls: "border-success text-kept" },
  accent: { title: "Almost: check the accents", cls: "border-blocked text-warning-text" },
  incorrect: { title: "Incorrect", cls: "border-failure text-error-text" },
} as const;

function split(value: string | null): string[] {
  return value ? value.split(",").map((s) => s.trim()).filter(Boolean) : [];
}

function BackToStation() {
  return (
    <Button asChild variant="secondary">
      <Link to="/practice/verbs">Back to the Verb Station</Link>
    </Button>
  );
}

function Marked({ text, other, tone }: { text: string; other: string; tone: string }) {
  const mask = diffMask(text, other);
  return (
    <>
      {Array.from(text).map((ch, i) => (
        <span key={i} className={mask[i] ? cn("rounded-sm font-bold underline decoration-2", tone) : undefined}>
          {ch}
        </span>
      ))}
    </>
  );
}

function Prompt({ item }: { item: DrillItem }) {
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 text-2xl text-heading">
      {item.subject && <span>{item.subject}</span>}
      {item.subject && <span aria-hidden>·</span>}
      <strong>{item.infinitive}</strong>
      {item.en && <span className="text-base text-detail">({item.en})</span>}
      <span aria-hidden>·</span>
      <em className="text-lg text-teal">{item.tense_label}</em>
    </p>
  );
}

function Summary({ entries, mode, onRestart }: { entries: Entry[]; mode: DrillMode; onRestart: () => void }) {
  const navigate = useNavigate();
  const correct = entries.filter((e) => e.result.result === "correct").length;
  const misses = entries.filter((e) => e.result.result !== "correct");
  const pct = entries.length ? Math.round((correct / entries.length) * 100) : 0;

  function practiceMistakes() {
    const verbs = [...new Set(misses.map((m) => m.item.infinitive))];
    const tenses = [...new Set(misses.map((m) => m.item.tense))];
    void navigate(drillUrl({ verbs, tenses, mode, count: Math.min(40, Math.max(5, misses.length)) }));
  }

  return (
    <div className="flex flex-col gap-6">
      <Card className="text-center">
        <h2 className="text-2xl">Drill complete</h2>
        <p className="mt-2 text-4xl font-bold text-heading" data-testid="score">
          {correct} / {entries.length}
        </p>
        <p className="text-detail">{pct}% correct</p>
      </Card>
      {misses.length > 0 && (
        <section aria-label="Misses" className="flex flex-col gap-3">
          <h3 className="text-xl">To review</h3>
          <ul className="flex flex-col gap-3">
            {misses.map((m, i) => (
              <li key={i} className="rounded-control border-l-4 border-failure bg-surface p-3 text-sm">
                <p className="text-heading">
                  {m.item.subject ? `${m.item.subject} · ` : ""}
                  <strong>{m.item.infinitive}</strong> · {m.item.tense_label}
                </p>
                <p>
                  Your answer: <span className="text-error-text">{m.answer || "(blank)"}</span>
                </p>
                <p>
                  Expected: <span className="font-bold text-kept">{m.result.expected}</span>
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="flex flex-wrap gap-3">
        {misses.length > 0 && (
          <Button type="button" onClick={practiceMistakes}>
            Practice my mistakes
          </Button>
        )}
        <Button type="button" variant="secondary" onClick={onRestart}>
          New drill
        </Button>
      </div>
    </div>
  );
}

function Runner({ items, mode }: { items: DrillItem[]; mode: DrillMode }) {
  const navigate = useNavigate();
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<VerbAnswerResult | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const shownAt = useRef(0);
  const item = items[index];
  const done = !item;

  useEffect(() => {
    if (!done) {
      shownAt.current = Date.now();
      inputRef.current?.focus();
    }
  }, [index, done]);

  const check = useMutation({
    mutationFn: () => {
      if (!item) throw new Error("No drill item");
      return submitVerbAnswers([
        {
          infinitive: item.infinitive,
          tense: item.tense,
          person: item.person,
          answer: answer.trim(),
          mode: item.mode,
          sentence: item.sentence
            ? { bank: item.sentence.bank, version: item.sentence.version, index: item.sentence.index }
            : undefined,
          time_spent_ms: Date.now() - shownAt.current,
        },
      ]);
    },
    onSuccess: ({ results }) => {
      const r = results[0];
      if (!r || !item) return;
      setResult(r);
      setEntries((prev) => [...prev, { item, answer: answer.trim(), result: r }]);
    },
  });

  if (!item) {
    return <Summary entries={entries} mode={mode} onRestart={() => void navigate("/practice/verbs")} />;
  }

  function next() {
    setResult(null);
    setAnswer("");
    check.reset();
    setIndex((i) => i + 1);
  }

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (result) next();
    else if (answer.trim() && !check.isPending) check.mutate();
  }

  const fb = result ? FEEDBACK[result.result] : null;
  const readOnly = !!result;
  const inputProps = {
    ref: inputRef,
    value: answer,
    readOnly,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setAnswer(e.target.value),
    autoComplete: "off",
    autoCapitalize: "none",
    spellCheck: false,
    "aria-label": "Your answer",
  } as const;
  const inputClass = cn(
    "h-12 rounded-control border bg-chrome px-3 text-lg text-heading focus-visible:border-purple",
    result
      ? result.result === "correct"
        ? "border-success"
        : result.result === "accent"
          ? "border-blocked"
          : "border-failure"
      : "border-line",
  );

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="mb-1 flex justify-between text-sm text-detail">
          <span>
            {index + 1} / {items.length}
          </span>
          {item.mode === "context" && <Badge variant="outline">In a sentence</Badge>}
        </div>
        <div
          role="progressbar"
          aria-label="Drill progress"
          aria-valuemin={0}
          aria-valuemax={items.length}
          aria-valuenow={index}
          className="h-2 overflow-hidden rounded-full bg-white/10"
        >
          <div className="h-full bg-purple transition-[width] duration-300 motion-reduce:transition-none" style={{ width: `${(index / items.length) * 100}%` }} />
        </div>
      </div>

      <Card>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" aria-label="Answer">
          {item.mode === "context" && item.sentence ? (
            <>
              <p className="text-sm text-detail">
                <strong className="text-heading">{item.infinitive}</strong>
                {item.en ? ` (${item.en})` : ""} · <em className="text-teal">{item.tense_label}</em>
              </p>
              <p className="flex flex-wrap items-center gap-x-1 gap-y-2 text-xl text-heading">
                <span>{item.sentence.before}</span>
                <input {...inputProps} className={cn(inputClass, "w-44 max-w-full")} />
                <span>{item.sentence.after}</span>
              </p>
              <p className="text-sm text-detail">{item.sentence.en}</p>
            </>
          ) : (
            <>
              <Prompt item={item} />
              <input {...inputProps} className={cn(inputClass, "w-full")} />
            </>
          )}

          {!result && <AccentKeys target={inputRef} onInsert={setAnswer} />}

          <div aria-live="polite" role="status">
            {check.isError && <p className="text-sm text-error-text">{apiErrorMessage(check.error)}</p>}
            {result && fb && (
              <div className={cn("flex flex-col gap-2 rounded-control border-l-4 bg-chrome p-4", fb.cls)} data-testid="feedback">
                <p className="font-bold">{fb.title}</p>
                {result.result !== "correct" && (
                  <p className="text-sm text-detail">
                    Your answer: <span className="text-heading">{<Marked text={answer.trim() || "(blank)"} other={result.expected} tone="text-error-text" />}</span>
                    <br />
                    Expected:{" "}
                    <span className="font-bold text-kept">
                      <Marked text={result.expected} other={answer.trim()} tone="text-kept" />
                    </span>
                  </p>
                )}
                {result.result === "correct" && <p className="text-sm text-heading">{result.expected}</p>}
                {result.message && <p className="text-sm text-detail">{result.message}</p>}
                <div className="flex items-center gap-1 text-sm text-detail">
                  <SpeakButton text={result.said} />
                  <span>{result.said}</span>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={check.isPending || (!result && !answer.trim())}>
              {result ? (index + 1 >= items.length ? "See results" : "Next") : "Check"}
            </Button>
            <span className="text-xs text-muted">Press Enter to {result ? "continue" : "check"}</span>
          </div>
        </form>
      </Card>
    </div>
  );
}

export function VerbDrillPage() {
  const [params] = useSearchParams();
  const location = useLocation();
  const tenses = split(params.get("tenses"));
  const verbs = split(params.get("verbs"));
  const set = params.get("set") ?? undefined;
  const rawMode = params.get("mode");
  const mode: DrillMode = rawMode === "form" || rawMode === "context" ? rawMode : "mixed";
  const count = Math.min(40, Math.max(1, Number(params.get("count")) || 10));
  const valid = tenses.length > 0 && (verbs.length > 0 || !!set);

  const request: DrillRequest = { tenses, mode, count, ...(verbs.length > 0 ? { verbs } : { set }) };
  const drill = useQuery({
    // location.key makes every navigation (even to the same URL) start a fresh drill.
    queryKey: ["verbs", "drill", location.key, location.search],
    queryFn: () => createDrill(request),
    enabled: valid,
    retry: false,
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-3xl">Verb drill</h1>
        <Link to="/practice/verbs" className="text-sm text-teal underline">
          Exit
        </Link>
      </div>

      {!valid && (
        <div className="flex flex-col items-start gap-3">
          <Alert>
            <AlertDescription>This drill link is missing verbs or tenses.</AlertDescription>
          </Alert>
          <BackToStation />
        </div>
      )}
      {valid && drill.isPending && <div role="status" aria-label="Preparing drill" className="h-48 animate-pulse rounded-card bg-surface" />}
      {drill.isError && (
        <div className="flex flex-col items-start gap-3">
          <Alert>
            <AlertDescription>
              {drill.error instanceof Error && "status" in drill.error && (drill.error as { status: number }).status === 400
                ? `Couldn’t build that drill: ${apiErrorMessage(drill.error)}`
                : `Couldn’t load the drill: ${apiErrorMessage(drill.error)}`}
            </AlertDescription>
          </Alert>
          <BackToStation />
        </div>
      )}
      {drill.data && drill.data.items.length === 0 && (
        <div className="flex flex-col items-start gap-3">
          <p>No questions were generated for that selection.</p>
          <BackToStation />
        </div>
      )}
      {drill.data && drill.data.items.length > 0 && <Runner key={drill.dataUpdatedAt} items={drill.data.items} mode={mode} />}
    </div>
  );
}
