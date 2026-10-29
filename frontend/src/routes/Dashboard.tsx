import { Link } from "react-router";
import { Flame } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ContinueCard } from "@/features/curriculum/ContinueCard";
import { useMe } from "@/features/auth/hooks";
import { VoiceCheckCard } from "@/features/audio/VoiceCheckCard";
import { HealthCard } from "@/features/health/HealthCard";
import { ActivityChart } from "@/features/progress/charts";
import { useDashboard } from "@/features/progress/hooks";
import { ReviewCard } from "@/features/progress/ReviewCard";
import type { Dashboard as DashboardData } from "@/lib/api/progress";

function Tile({ label, value, detail, to }: { label: string; value: string; detail?: string; to?: string }) {
  const body = (
    <>
      <dt className="order-2 text-sm text-detail">{label}</dt>
      <dd className="order-1 text-3xl font-bold tabular-nums text-heading">{value}</dd>
      {detail && <dd className="order-3 text-xs text-muted">{detail}</dd>}
    </>
  );
  return to ? (
    <Link to={to} className="flex h-full flex-col rounded-card bg-surface p-4 transition-colors hover:bg-chrome focus-visible:outline-2 focus-visible:outline-purple">
      <dl className="flex flex-col">{body}</dl>
    </Link>
  ) : (
    <dl className="flex h-full flex-col rounded-card bg-surface p-4">{body}</dl>
  );
}

function Tiles({ data }: { data: DashboardData }) {
  const { streak, minutes, accuracy_week: accuracy, vocab } = data;
  const due = vocab.due_now + vocab.new_today;
  return (
    <section aria-label="Today at a glance" className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <div className="relative">
        <Tile
          label="day streak"
          value={String(streak.current)}
          detail={
            streak.studied_today
              ? `Best: ${streak.longest} days`
              : streak.current
                ? "Practise today to keep it going"
                : `Best: ${streak.longest} days`
          }
        />
        {streak.studied_today && <Flame aria-hidden className="absolute right-4 top-4 size-5 text-warning-text" />}
      </div>
      <Tile label="minutes today" value={String(minutes.today)} detail={`${minutes.week} min this week`} />
      <Tile
        label="accuracy this week"
        value={accuracy.accuracy === null ? "–" : `${Math.round(accuracy.accuracy * 100)}%`}
        detail={`${accuracy.graded} graded answers`}
      />
      <Tile
        label="vocabulary cards to review"
        value={String(due)}
        detail={`${vocab.due_now} due, ${vocab.new_today} new`}
        to="/practice/vocab/review"
      />
    </section>
  );
}

export function Dashboard() {
  const me = useMe();
  const dashboard = useDashboard();
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-3xl">Bonjour, {me.data?.username}</h1>
      {dashboard.isPending && <div role="status" aria-label="Loading your progress" className="h-28 animate-pulse rounded-card bg-surface" />}
      {dashboard.isError && <p className="text-sm text-error-text">Couldn’t load your progress: {dashboard.error.message}</p>}
      {dashboard.data && <Tiles data={dashboard.data} />}
      <div className="grid gap-6 md:grid-cols-2">
        <ContinueCard />
        {dashboard.data && <ReviewCard data={dashboard.data} />}
        {dashboard.data && (
          <Card>
            <CardHeader>
              <CardTitle>Last two weeks</CardTitle>
              <CardDescription>
                Exercises, verb drills and flashcards per day.{" "}
                <Link to="/progress" className="text-teal underline">
                  See your progress
                </Link>
              </CardDescription>
            </CardHeader>
            <ActivityChart days={dashboard.data.history} />
          </Card>
        )}
        <HealthCard />
        <VoiceCheckCard />
      </div>
    </div>
  );
}
