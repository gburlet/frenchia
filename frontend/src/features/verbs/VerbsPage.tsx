import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { X } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { DrillMode, VerbIndex, VerbProgress } from "@/lib/api/verbs";
import { useVerbIndex, useVerbProgress } from "./hooks";
import { AuxBadge } from "./AuxBadge";
import { drillUrl, fold } from "./utils";

const selectClass =
  "h-11 w-full rounded-control border border-line bg-chrome px-3 text-base text-heading focus-visible:border-purple";
const MODES: { value: DrillMode; label: string }[] = [
  { value: "mixed", label: "Mixed" },
  { value: "form", label: "Forms only" },
  { value: "context", label: "In sentences" },
];
const COUNTS = [10, 20, 30];
const LEVELS = ["A1", "A2", "B1", "B2"];

function ProgressSummary({ progress }: { progress: VerbProgress }) {
  const accuracy = progress.attempts > 0 ? Math.round((progress.correct / progress.attempts) * 100) : null;
  const navigate = useNavigate();
  const spots = progress.weak_spots;
  const drillSpots = () => {
    const verbs = [...new Set(spots.map((s) => s.infinitive))].slice(0, 6);
    const tenses = [...new Set(spots.map((s) => s.tense))];
    void navigate(drillUrl({ verbs, tenses, mode: "mixed", count: 10 }));
  };
  return (
    <Card aria-label="Your progress" className="flex flex-col gap-4">
      <dl className="grid grid-cols-3 gap-3 text-center">
        <div>
          <dd className="text-2xl font-bold text-heading">{progress.attempts}</dd>
          <dt className="text-xs text-detail">Attempts</dt>
        </div>
        <div>
          <dd className="text-2xl font-bold text-heading">{accuracy === null ? "–" : `${accuracy}%`}</dd>
          <dt className="text-xs text-detail">Accuracy</dt>
        </div>
        <div>
          <dd className="text-2xl font-bold text-heading">{progress.verbs_practiced}</dd>
          <dt className="text-xs text-detail">Verbs practised</dt>
        </div>
      </dl>
      {spots.length > 0 && (
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base">Weak spots</h2>
            <Button type="button" variant="secondary" onClick={drillSpots}>
              Drill these
            </Button>
          </div>
          <ul className="flex flex-wrap gap-2">
            {spots.map((s) => (
              <li key={`${s.slug}-${s.tense}`}>
                <Link
                  to={`/practice/verbs/${s.slug}`}
                  className="inline-flex items-center gap-1 rounded-full border border-line px-3 py-1 text-sm text-heading hover:border-teal"
                >
                  <span className="font-bold">{s.infinitive}</span>
                  <span className="text-detail">· {s.tense_label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function DrillBuilder({ index }: { index: VerbIndex }) {
  const navigate = useNavigate();
  const [source, setSource] = useState<"set" | "verbs">("set");
  const [setChoice, setSetChoice] = useState<string | null>(null);
  const [chosenTenses, setChosenTenses] = useState<string[] | null>(null);
  const [mode, setMode] = useState<DrillMode>("mixed");
  const [count, setCount] = useState(10);
  const [picked, setPicked] = useState<string[]>([]);
  const [pickQuery, setPickQuery] = useState("");

  const setId = setChoice ?? index.sets[0]?.id ?? null;
  const activeSet = index.sets.find((s) => s.id === setId);
  const drillTenses = index.tenses.filter((t) => t.drill);
  const tenses = chosenTenses ?? activeSet?.tenses ?? [];
  const byInfinitive = useMemo(() => new Map(index.verbs.map((v) => [v.infinitive, v])), [index.verbs]);

  const suggestions = useMemo(() => {
    const q = fold(pickQuery.trim());
    if (!q) return [];
    return index.verbs
      .filter((v) => !picked.includes(v.infinitive) && (fold(v.infinitive).includes(q) || fold(v.en ?? "").includes(q)))
      .slice(0, 8);
  }, [index.verbs, pickQuery, picked]);

  function toggleTense(key: string) {
    setChosenTenses(tenses.includes(key) ? tenses.filter((t) => t !== key) : [...tenses, key]);
  }
  function chooseSet(id: string) {
    setSource("set");
    setSetChoice(id);
    setChosenTenses(null);
  }

  const ready = tenses.length > 0 && (source === "set" ? !!setId : picked.length > 0);
  function start() {
    if (!ready) return;
    void navigate(drillUrl({ set: source === "set" ? setId : null, verbs: source === "verbs" ? picked : [], tenses, mode, count }));
  }

  return (
    <form
      aria-label="Drill builder"
      className="flex flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        start();
      }}
    >
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-base font-bold text-heading">1. Choose verbs</legend>
        <div className="flex gap-2" role="radiogroup" aria-label="Verb source">
          {(["set", "verbs"] as const).map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={source === s}
              onClick={() => setSource(s)}
              className={cn(
                "cursor-pointer rounded-full border px-4 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-purple",
                source === s ? "border-purple bg-purple text-heading" : "border-line text-detail",
              )}
            >
              {s === "set" ? "A verb set" : "Specific verbs"}
            </button>
          ))}
        </div>

        {source === "set" ? (
          <ul className="grid gap-3 sm:grid-cols-2" aria-label="Verb sets">
            {index.sets.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  aria-pressed={setId === s.id}
                  onClick={() => chooseSet(s.id)}
                  className={cn(
                    "flex h-full w-full cursor-pointer flex-col gap-1 rounded-card border bg-surface p-4 text-left focus-visible:outline-2 focus-visible:outline-purple",
                    setId === s.id ? "border-purple" : "border-card-border hover:border-teal",
                  )}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-heading font-bold text-heading">{s.title}</span>
                    <Badge variant="teal">{s.level}</Badge>
                  </span>
                  <span className="text-sm text-detail">{s.title_en}</span>
                  <span className="text-sm">{s.description}</span>
                  <span className="text-xs text-muted">{s.verbs.length} verbs</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="flex flex-col gap-2">
            <label htmlFor="verb-pick" className="text-sm text-detail">
              Search verbs to add
            </label>
            <Input
              id="verb-pick"
              value={pickQuery}
              onChange={(e) => setPickQuery(e.target.value)}
              placeholder="aller, to go…"
              autoComplete="off"
            />
            {suggestions.length > 0 && (
              <ul className="flex flex-wrap gap-2" aria-label="Matching verbs">
                {suggestions.map((v) => (
                  <li key={v.infinitive}>
                    <button
                      type="button"
                      onClick={() => {
                        setPicked([...picked, v.infinitive]);
                        setPickQuery("");
                      }}
                      className="cursor-pointer rounded-full border border-line px-3 py-1 text-sm text-heading hover:border-teal focus-visible:outline-2 focus-visible:outline-purple"
                    >
                      + {v.infinitive}
                      {v.en ? <span className="text-detail"> ({v.en})</span> : null}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <ul className="flex flex-wrap gap-2" aria-label="Selected verbs">
              {picked.map((inf) => (
                <li key={inf}>
                  <button
                    type="button"
                    aria-label={`Remove ${inf}`}
                    onClick={() => setPicked(picked.filter((p) => p !== inf))}
                    className="inline-flex cursor-pointer items-center gap-1 rounded-full bg-purple px-3 py-1 text-sm text-heading focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                  >
                    {byInfinitive.get(inf)?.infinitive ?? inf}
                    <X aria-hidden className="size-3" />
                  </button>
                </li>
              ))}
              {picked.length === 0 && <li className="text-sm text-muted">No verbs selected yet.</li>}
            </ul>
          </div>
        )}
      </fieldset>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-base font-bold text-heading">2. Tenses</legend>
        {LEVELS.map((level) => {
          const group = drillTenses.filter((t) => t.level === level);
          if (group.length === 0) return null;
          return (
            <div key={level} role="group" aria-label={`${level} tenses`} className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className="w-8 text-sm font-bold text-teal">{level}</span>
              {group.map((t) => (
                <label key={t.key} className="inline-flex cursor-pointer items-center gap-2 text-sm text-heading">
                  <input
                    type="checkbox"
                    checked={tenses.includes(t.key)}
                    onChange={() => toggleTense(t.key)}
                    className="size-4 accent-purple"
                  />
                  <span>{t.label}</span>
                  <span className="text-xs text-muted">{t.mood !== "Indicatif" ? t.mood : ""}</span>
                </label>
              ))}
            </div>
          );
        })}
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-base font-bold text-heading">3. Options</legend>
        <div>
          <label htmlFor="drill-mode" className="mb-1 block text-sm text-detail">
            Mode
          </label>
          <select id="drill-mode" className={selectClass} value={mode} onChange={(e) => setMode(e.target.value as DrillMode)}>
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="drill-count" className="mb-1 block text-sm text-detail">
            Questions
          </label>
          <select id="drill-count" className={selectClass} value={count} onChange={(e) => setCount(Number(e.target.value))}>
            {COUNTS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </fieldset>

      <Button type="submit" disabled={!ready} fullWidth>
        Start drill
      </Button>
    </form>
  );
}

function VerbBrowser({ index }: { index: VerbIndex }) {
  const [query, setQuery] = useState("");
  const [setFilter, setSetFilter] = useState("");
  const [aux, setAux] = useState("");
  const [limit, setLimit] = useState(60);

  const filtered = useMemo(() => {
    const q = fold(query.trim());
    return index.verbs.filter(
      (v) =>
        (!q || fold(v.infinitive).includes(q) || fold(v.en ?? "").includes(q)) &&
        (!setFilter || v.sets.includes(setFilter)) &&
        (!aux || v.auxiliary === aux),
    );
  }, [index.verbs, query, setFilter, aux]);

  return (
    <section aria-label="Verb browser" className="flex flex-col gap-4">
      <h2 className="text-2xl">All verbs</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label htmlFor="browse-q" className="mb-1 block text-sm text-detail">
            Search verbs
          </label>
          <Input
            id="browse-q"
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setLimit(60);
            }}
            placeholder="infinitive or English"
          />
        </div>
        <div>
          <label htmlFor="browse-set" className="mb-1 block text-sm text-detail">
            Set
          </label>
          <select id="browse-set" className={selectClass} value={setFilter} onChange={(e) => setSetFilter(e.target.value)}>
            <option value="">All sets</option>
            {index.sets.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="browse-aux" className="mb-1 block text-sm text-detail">
            Auxiliary
          </label>
          <select id="browse-aux" className={selectClass} value={aux} onChange={(e) => setAux(e.target.value)}>
            <option value="">Any auxiliary</option>
            <option value="avoir">avoir</option>
            <option value="être">être</option>
            <option value="both">both</option>
          </select>
        </div>
      </div>
      <p className="text-sm text-muted" aria-live="polite">
        {filtered.length} verb{filtered.length === 1 ? "" : "s"}
      </p>
      <ul className="grid gap-2 sm:grid-cols-2" aria-label="Verbs">
        {filtered.slice(0, limit).map((v) => (
          <li key={v.slug}>
            <Link
              to={`/practice/verbs/${v.slug}`}
              className="flex flex-wrap items-center gap-2 rounded-control border border-card-border bg-surface px-4 py-3 hover:border-teal"
            >
              <span className="font-heading font-bold text-heading">{v.infinitive}</span>
              {v.en && <span className="text-sm text-detail">{v.en}</span>}
              <span className="ml-auto flex gap-1.5">
                <AuxBadge auxiliary={v.auxiliary} />
                {v.pronominal && <Badge variant="outline">pronominal</Badge>}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {filtered.length > limit && (
        <Button type="button" variant="ghost" onClick={() => setLimit(limit + 60)} className="self-start">
          Show more
        </Button>
      )}
    </section>
  );
}

export function VerbsPage() {
  const index = useVerbIndex();
  const progress = useVerbProgress();

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl">Verb Station</h1>
        <p className="text-detail">
          Conjugate on purpose. Pick some verbs and tenses, then drill the forms or fill the blank in real sentences.
        </p>
      </header>

      {progress.data && <ProgressSummary progress={progress.data} />}

      {index.isPending && <div role="status" aria-label="Loading verbs" className="h-48 animate-pulse rounded-card bg-surface" />}
      {index.isError && (
        <Alert>
          <AlertDescription>Couldn’t load the verbs: {index.error.message}</AlertDescription>
        </Alert>
      )}
      {index.data && (
        <>
          <section aria-label="Build a drill" className="flex flex-col gap-4">
            <h2 className="text-2xl">Build a drill</h2>
            <DrillBuilder index={index.data} />
          </section>
          <VerbBrowser index={index.data} />
        </>
      )}
    </div>
  );
}
