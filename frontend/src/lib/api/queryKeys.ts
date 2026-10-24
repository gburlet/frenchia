import type { TranslateFilters } from "./types";

export const queryKeys = {
  me: ["auth", "me"] as const,
  health: ["health"] as const,
  curriculum: ["curriculum"] as const,
  lesson: (id: string) => ["lesson", id] as const,
  translateOptions: ["practice", "translate", "options"] as const,
  translateNext: (filters: TranslateFilters) => ["practice", "translate", "next", filters] as const,
};
