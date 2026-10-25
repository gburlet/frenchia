import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { AccentKeys } from "@/components/AccentKeys";
import { SpeakButton } from "@/features/audio/SpeakButton";
import { ApiError } from "@/lib/api/client";
import { submitVerbAnswers } from "@/lib/api/verbs";
import type { TenseTable, VerbAnswerResult, VerbDetail, VerbExample } from "@/lib/api/verbs";
import { cn } from "@/lib/utils";
import { AuxBadge } from "./AuxBadge";
import { useVerb } from "./hooks";
import { apiErrorMessage, drillUrl } from "./utils";

const RESULT_STYLE = {
  correct: { text: "Correct", cls: "text-kept", variant: "success" },
  accent: { text: "Check the accents", cls: "text-warning-text", variant: "blocked" },
  incorrect: { text: "Incorrect", cls: "text-error-text", variant: "failure" },
} as const;

function Highlighted({ example }: { example: VerbExample }) {
  const at = example.form ? example.fr.indexOf(example.form) : -1;
  if (at < 0) return <>{example.fr}</>;
  return (
    <>
      {example.fr.slice(0, at)}
      <mark className="rounded-sm bg-purple/30 px-0.5 font-bold text-heading">{example.form}</mark>
      {example.fr.slice(at + example.form.length)}
    </>
  );
}

function Meter({ value, label }: { value: number; label: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <span
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className="inline-block h-1.5 w-16 overflow-hidden rounded-full bg-white/10 align-middle"
    >
      <span className="block h-full bg-success" style={{ width: `${pct}%` }} />
    </span>
  );
}

function QuizRow({
  person,
  verb,
  value,
  onChange,
  result,
  disabled,
  registerRef,
}: {
  person: string;
  verb: string;
  value: string;
  onChange: (v: string) => void;
  result?: VerbAnswerResult;
  disabled: boolean;
  registerRef: (el: HTMLInputElement | null) => void;
}) {
  const style = result ? RESULT_STYLE[result.result] : null;
  const id = `quiz-${verb}-${person}`;
  return (
    <tr className="border-t border-line align-top">
      <th scope="row" className="py-2 pr-3 text-left font-normal text-detail">
        <label htmlFor={id}>{person}</label>
      </th>
      <td className="py-2">
        <input
          id={id}
          ref={registerRef}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          className={cn(
            "h-10 w-full rounded-control border bg-chrome px-3 text-heading focus-visible:border-purple",
            result ? (result.result === "correct" ? "border-success" : result.result === "accent" ? "border-blocked" : "border-failure") : "border-line",
          )}
        />
        {result && style && (
          <p className={cn("mt-1 text-sm", style.cls)} data-testid={`quiz-result-${person}`}>
            <span className="font-bold">{style.text}</span>
            {result.result !== "correct" && (
              <>
                {" "}
                · expected <span className="font-bold text-heading">{result.expected}</span>
              </>
            )}
            {result.message && result.result !== "correct" && <span className="text-detail"> · {result.message}</span>}
          </p>
        )}
      </td>
    </tr>
  );
}

function TenseQuiz({ verb, table, onClose }: { verb: VerbDetail; table: TenseTable; onClose: () => void }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<VerbAnswerResult[] | null>(null);
  const activeInput = useRef<HTMLInputElement | null>(null);
  const [active, setActive] = useState(table.rows[0]?.person ?? "");
  const startedAt = useRef(0);
  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  const check = useMutation({
    mutationFn: () =>
      submitVerbAnswers(
        table.rows.map((r) => ({
          infinitive: verb.infinitive,
          tense: table.tense,
          person: r.person,
          answer: answers[r.person] ?? "",
          mode: "table" as const,
          time_spent_ms: Date.now() - startedAt.current,
        })),
      ),
    onSuccess: (data) => setResults(data.results),
  });

  function retry() {
    setAnswers({});
    setResults(null);
    check.reset();
    startedAt.current = Date.now();
  }
  const score = results?.filter((r) => r.result === "correct").length ?? 0;

  return (
    <form
      aria-label={`Quiz: ${table.label}`}
      className="mt-3 flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!results) check.mutate();
      }}
    >
      <table className="w-full text-base">
        <tbody>
          {table.rows.map((row, i) => (
            <QuizRow
              key={row.person}
              person={row.person}
              verb={verb.slug}
              value={answers[row.person] ?? ""}
              onChange={(v) => {
                setAnswers({ ...answers, [row.person]: v });
              }}
              result={results?.[i]}
              disabled={!!results || check.isPending}
              registerRef={(el) => {
                if (el) {
                  el.onfocus = () => {
                    activeInput.current = el;
                    setActive(row.person);
                  };
                }
              }}
            />
          ))}
        </tbody>
      </table>
      {!results && <AccentKeys target={activeInput} onInsert={(v) => setAnswers({ ...answers, [active]: v })} />}
      <div aria-live="polite">
        {results && (
          <p className="text-heading">
            {score} / {results.length} correct
          </p>
        )}
        {check.isError && <p className="text-sm text-error-text">{apiErrorMessage(check.error)}</p>}
      </div>
      <div className="flex flex-wrap gap-3">
        {!results ? (
          <Button type="submit" disabled={check.isPending}>
            Check
          </Button>
        ) : (
          <Button type="button" onClick={retry}>
            Try again
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={onClose}>
          Close quiz
        </Button>
      </div>
    </form>
  );
}

function TenseCard({ verb, table, quizzing, onQuiz, mastery }: {
  verb: VerbDetail;
  table: TenseTable;
  quizzing: boolean;
  onQuiz: (key: string | null) => void;
  mastery?: { attempts: number; ewma: number };
}) {
  const literary = table.tense === "indicatif.passe_simple";
  return (
    <Card className={cn("p-4 sm:p-5", literary && "opacity-70")} aria-label={table.label}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg">{table.label}</h3>
        <span className="text-sm text-muted">{table.label_en}</span>
        <Badge variant="teal">{table.level}</Badge>
        {literary && <Badge variant="outline">literary</Badge>}
        {mastery && (
          <span className="flex items-center gap-1.5 text-xs text-muted">
            <Meter value={mastery.ewma} label={`Mastery of ${table.label}`} />
            {mastery.attempts} tries
          </span>
        )}
        {!quizzing && (
          <Button type="button" variant="ghost" className="ml-auto h-8 px-3 text-xs" onClick={() => onQuiz(table.tense)} aria-label={`Quiz this tense: ${table.label}`}>
            Quiz this tense
          </Button>
        )}
      </div>
      {quizzing ? (
        <TenseQuiz key={table.tense} verb={verb} table={table} onClose={() => onQuiz(null)} />
      ) : (
        <table className="mt-3 w-full text-base">
          <tbody>
            {table.rows.map((row) => (
              <tr key={row.person} className="border-t border-line">
                <th scope="row" className="w-14 py-1.5 pr-3 text-left font-normal text-detail">
                  {row.person}
                </th>
                <td className="py-1.5 text-heading">
                  {row.form}
                  {row.variants.length > 0 && <span className="ml-2 text-sm text-muted">also: {row.variants.join(", ")}</span>}
                </td>
                <td className="w-10 py-0.5 text-right">
                  <SpeakButton text={row.said} className="size-8" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

export function VerbDetailPage() {
  const { slug = "" } = useParams();
  const query = useVerb(slug);
  const [quiz, setQuiz] = useState<string | null>(null);

  if (query.isPending) {
    return <div role="status" aria-label="Loading verb" className="mx-auto h-64 max-w-4xl animate-pulse rounded-card bg-surface" />;
  }
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="mx-auto flex max-w-4xl flex-col items-start gap-3">
        <Alert>
          <AlertDescription>{notFound ? "That verb isn’t in the station." : `Couldn’t load the verb: ${query.error.message}`}</AlertDescription>
        </Alert>
        <Button asChild variant="secondary">
          <Link to="/practice/verbs">Back to the Verb Station</Link>
        </Button>
      </div>
    );
  }

  const verb = query.data;
  const masteryBy = new Map(verb.mastery.map((m) => [m.tense, m]));
  const moods: { mood: string; tables: TenseTable[] }[] = [];
  for (const t of verb.table) {
    const last = moods[moods.length - 1];
    if (last && last.mood === t.mood) last.tables.push(t);
    else moods.push({ mood: t.mood, tables: [t] });
  }
  const easy = verb.table.filter((t) => (t.level === "A1" || t.level === "A2") && t.tense !== "indicatif.passe_simple").map((t) => t.tense);
  const drillTenses = easy.length > 0 ? easy : verb.mastery.map((m) => m.tense);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8">
      <p>
        <Link to="/practice/verbs" className="text-sm text-teal underline">
          ← Verb Station
        </Link>
      </p>
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-4xl">{verb.infinitive}</h1>
          <SpeakButton text={verb.infinitive} />
          <AuxBadge auxiliary={verb.auxiliary} />
          {verb.pronominal && <Badge variant="outline">pronominal</Badge>}
        </div>
        {verb.en && <p className="text-lg text-detail">{verb.en}</p>}
        <p className="text-sm text-detail">
          Past participle: <span className="font-bold text-heading">{verb.participle_past}</span> · Present participle:{" "}
          <span className="font-bold text-heading">{verb.participle_present}</span>
        </p>
        {verb.note && <p className="rounded-control bg-surface p-3 text-sm">{verb.note}</p>}
        <div>
          <Button asChild>
            <Link to={drillUrl({ verbs: [verb.infinitive], tenses: drillTenses })}>Drill this verb</Link>
          </Button>
        </div>
      </header>

      {moods.map(({ mood, tables }) => (
        <section key={mood} aria-label={mood} className="flex flex-col gap-4">
          <h2 className="text-2xl">{mood}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {tables.map((t) => (
              <div key={t.tense} className={quiz === t.tense ? "md:col-span-2" : undefined}>
                <TenseCard verb={verb} table={t} quizzing={quiz === t.tense} onQuiz={setQuiz} mastery={masteryBy.get(t.tense)} />
              </div>
            ))}
          </div>
        </section>
      ))}

      {verb.examples.length > 0 && (
        <section aria-label="Examples" className="flex flex-col gap-3">
          <h2 className="text-2xl">Examples</h2>
          <ul className="flex flex-col gap-3">
            {verb.examples.map((ex, i) => (
              <li key={i} className="flex items-start gap-2 rounded-control border border-card-border bg-surface p-3">
                <div className="flex-1">
                  <p className="text-heading">
                    <Highlighted example={ex} />
                  </p>
                  <p className="text-sm text-detail">{ex.en}</p>
                  <p className="mt-1 flex items-center gap-2 text-xs text-muted">
                    {ex.tense_label}
                    {ex.region === "qc" && <Badge variant="teal">QC</Badge>}
                  </p>
                </div>
                <SpeakButton text={ex.fr} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
