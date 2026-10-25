import { Badge } from "@/components/ui/badge";
import type { VerbSummary } from "@/lib/api/verbs";

export function AuxBadge({ auxiliary }: { auxiliary: VerbSummary["auxiliary"] }) {
  return <Badge variant="outline">{auxiliary === "both" ? "être / avoir" : auxiliary}</Badge>;
}
