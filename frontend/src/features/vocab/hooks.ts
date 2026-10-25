import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchVocabSet, fetchVocabSets, learnVocabSet } from "@/lib/api/vocab";

export const vocabKeys = {
  all: ["vocab"] as const,
  sets: ["vocab", "sets"] as const,
  set: (slug: string) => ["vocab", "set", slug] as const,
  review: (batch: number, ahead: boolean) => ["vocab", "review", batch, ahead] as const,
};

export function useVocabSets(enabled = true) {
  return useQuery({
    queryKey: vocabKeys.sets,
    queryFn: ({ signal }) => fetchVocabSets(signal),
    enabled,
  });
}

export function useVocabSet(slug: string) {
  return useQuery({
    queryKey: vocabKeys.set(slug),
    queryFn: ({ signal }) => fetchVocabSet(slug, signal),
  });
}

export function useLearnSet(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => learnVocabSet(slug),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: vocabKeys.set(slug) });
      void queryClient.invalidateQueries({ queryKey: vocabKeys.sets });
    },
  });
}
