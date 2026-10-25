import { Link } from "react-router";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Dashboard } from "@/lib/api/progress";
import { ActivityChart, Meter } from "./charts";
import { useDashboard } from "./hooks";

function Topics({ data }: { data: Dashboard }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Grammar topics</CardTitle>
        <CardDescription>Recent accuracy (newer answers count more), weakest first.</CardDescription>
      </CardHeader>
      {data.topics.length === 0 ? (
        <p className="text-sm text-detail">
          Answer some lesson or translation exercises and your topics will show up here.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {data.topics.map((t) => (
            <li key={t.id} className="flex flex-col gap-1">
              <span className="flex items-center gap-2">
                <span className="text-heading">{t.title}</span>
                <Badge variant="outline">{t.level}</Badge>
                <span className="ml-auto text-xs text-muted">{t.attempts} answers</span>
              </span>
              <Meter value={t.accuracy} label={`${t.title}: recent accuracy`} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Verbs({ data }: { data: Dashboard }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Verb tenses</CardTitle>
        <CardDescription>From the Verb Station drills.</CardDescription>
      </CardHeader>
      {data.verb_tenses.length === 0 ? (
        <p className="text-sm text-detail">
          No drills yet. <Link to="/practice/verbs" className="text-teal underline">Try the Verb Station</Link>
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {data.verb_tenses.map((t) => (
            <li key={t.tense} className="flex flex-col gap-1">
              <span className="flex items-center gap-2">
                <span className="text-heading">{t.label}</span>
                <span className="ml-auto text-xs text-muted">{t.attempts} answers</span>
              </span>
              <Meter value={t.accuracy} label={`${t.label}: recent accuracy`} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Overview({ data }: { data: Dashboard }) {
  const rows: [string, string][] = [
    ["Lessons completed", `${data.lessons.completed} of ${data.lessons.published}`],
    ["Current streak", `${data.streak.current} days (best ${data.streak.longest})`],
    ["Study time this week", `${data.minutes.week} min`],
    ["Words in your deck", String(data.vocab.words)],
    ["Well-known cards", String(data.vocab.mature)],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Overview</CardTitle>
      </CardHeader>
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-detail">{k}</dt>
            <dd className="text-right tabular-nums text-heading">{v}</dd>
          </div>
        ))}
      </dl>
      {data.mistakes.length > 0 && (
        <>
          <h3 className="mt-6 mb-2 text-base">Most common mistakes (30 days)</h3>
          <ul className="flex flex-wrap gap-2">
            {data.mistakes.map((m) => (
              <li key={m.category}>
                <Badge variant="outline">
                  {m.category.replaceAll("_", " ")} · {m.count}
                </Badge>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

export function ProgressPage() {
  const { data, isPending, isError, error } = useDashboard();
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl">Progress</h1>
      {isPending && <div role="status" aria-label="Loading your progress" className="h-64 animate-pulse rounded-card bg-surface" />}
      {isError && (
        <Alert>
          <AlertDescription>Couldn’t load your progress: {error.message}</AlertDescription>
        </Alert>
      )}
      {data && (
        <div className="grid gap-6 md:grid-cols-2">
          <Overview data={data} />
          <Card>
            <CardHeader>
              <CardTitle>Activity</CardTitle>
              <CardDescription>Items practised per day.</CardDescription>
            </CardHeader>
            <ActivityChart days={data.history} />
          </Card>
          <Topics data={data} />
          <Verbs data={data} />
        </div>
      )}
    </div>
  );
}
