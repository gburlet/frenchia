import { Link, useNavigate } from "react-router";
import { ArrowRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Dashboard } from "@/lib/api/progress";
import { ApiError } from "@/lib/api/client";
import { useStartReview } from "./hooks";

export function ReviewCard({ data }: { data: Dashboard }) {
  const navigate = useNavigate();
  const start = useStartReview();
  const review = data.review;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Review your weak spots</CardTitle>
        <CardDescription>Exercises on the topics you find hardest, plus new ones written for you.</CardDescription>
      </CardHeader>
      {review ? (
        <Link
          to="/practice/review"
          className="flex items-center justify-between gap-3 rounded-control border border-line px-4 py-3 transition-colors hover:bg-white/5"
        >
          <span>
            <span className="font-heading font-bold text-heading">Continue your review</span>{" "}
            <span className="text-sm text-muted">
              {review.answered}/{review.items} done
            </span>
          </span>
          <ArrowRight aria-hidden className="size-5 text-teal" />
        </Link>
      ) : (
        <div className="flex flex-col gap-3">
          {data.weak_topics.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {data.weak_topics.map((t) => (
                <li key={t.id}>
                  <span className="font-bold text-heading">{t.title}</span>
                  <span className="block text-sm text-muted">{t.reason}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-detail">
              No weak spots yet. A review will go over the lessons you’ve started.
            </p>
          )}
          <Button
            variant="secondary"
            className="self-start"
            disabled={start.isPending}
            onClick={() => start.mutate(undefined, { onSuccess: () => void navigate("/practice/review") })}
          >
            {start.isPending && <Loader2 aria-hidden className="size-4 animate-spin" />}
            Start a review
          </Button>
          {start.isError && (
            <p role="alert" className="text-sm text-error-text">
              {start.error instanceof ApiError ? start.error.detail : "Couldn’t start a review."}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
