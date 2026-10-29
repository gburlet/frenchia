import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { progressKeys } from "@/features/progress/hooks";
import {
  addVocabWord,
  fetchVocabSet,
  fetchVocabSets,
  learnVocabSet,
  removeVocabLexeme,
  removeVocabSet,
} from "@/lib/api/vocab";

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

function useDeckMutation<T>(mutationFn: () => Promise<T>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      // other sets' statuses and the dashboard tile change too
      void queryClient.invalidateQueries({ queryKey: vocabKeys.all });
      void queryClient.invalidateQueries({ queryKey: progressKeys.dashboard });
    },
  });
}

export function useLearnSet(slug: string) {
  return useDeckMutation(() => learnVocabSet(slug));
}

export function useRemoveSet(slug: string) {
  return useDeckMutation(() => removeVocabSet(slug));
}

/** Add one word to the deck, or remove it. */
export function useWordInDeck(lexemeId: number, inDeck: boolean) {
  return useDeckMutation<{ lexeme: number }>(() => (inDeck ? removeVocabLexeme(lexemeId) : addVocabWord(lexemeId)));
}
