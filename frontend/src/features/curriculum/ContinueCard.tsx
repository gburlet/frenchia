import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { findContinueLesson, useCurriculum } from "./hooks";

export function ContinueCard() {
  const query = useCurriculum();
  const found = query.data ? findContinueLesson(query.data) : null;
  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>Continue</CardTitle>
        <CardDescription>Pick up where you left off.</CardDescription>
      </CardHeader>
      {query.isPending && <div role="status" aria-label="Loading" className="h-10 animate-pulse rounded bg-chrome" />}
      {query.isError && <p className="text-sm text-error-text">Couldn’t load your lessons.</p>}
      {query.data && !found && (
        <p className="text-detail">
          Nothing to continue yet.{" "}
          <Link to="/curriculum" className="text-teal underline">Browse the curriculum</Link>
        </p>
      )}
      {found && (
        <Link
          to={`/lessons/${found.lesson.id}`}
          className="flex items-center justify-between gap-3 rounded-control border border-line px-4 py-3 transition-colors hover:bg-white/5"
        >
          <span className="flex flex-wrap items-center gap-2">
            <Badge variant="teal">{found.level}</Badge>
            <span className="font-heading font-bold text-heading">{found.lesson.title}</span>
            <span className="text-sm text-muted">{found.inProgress ? "In progress" : "Next up"}</span>
          </span>
          <ArrowRight aria-hidden className="size-5 text-teal" />
        </Link>
      )}
    </Card>
  );
}
