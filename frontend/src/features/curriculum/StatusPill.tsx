import { Badge } from "@/components/ui/badge";
import type { CurriculumLesson } from "@/lib/api/types";

export function StatusPill({ lesson }: { lesson: Pick<CurriculumLesson, "published" | "progress"> }) {
  if (!lesson.published) {
    return (
      <Badge variant="outline" className="opacity-70">
        Bientôt
      </Badge>
    );
  }
  switch (lesson.progress.status) {
    case "completed":
      return <Badge variant="success">Completed</Badge>;
    case "in_progress":
      return <Badge variant="teal">In progress</Badge>;
    default:
      return <Badge variant="neutral">Not started</Badge>;
  }
}
