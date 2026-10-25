import { useQuery } from "@tanstack/react-query";
import { fetchVerb, fetchVerbIndex, fetchVerbProgress } from "@/lib/api/verbs";

export const verbKeys = {
  index: ["verbs", "index"] as const,
  progress: ["verbs", "progress"] as const,
  detail: (slug: string) => ["verbs", "detail", slug] as const,
};

export function useVerbIndex() {
  return useQuery({ queryKey: verbKeys.index, queryFn: ({ signal }) => fetchVerbIndex(signal), staleTime: 5 * 60_000 });
}

export function useVerbProgress() {
  return useQuery({ queryKey: verbKeys.progress, queryFn: ({ signal }) => fetchVerbProgress(signal) });
}

export function useVerb(slug: string) {
  return useQuery({ queryKey: verbKeys.detail(slug), queryFn: ({ signal }) => fetchVerb(slug, signal) });
}
