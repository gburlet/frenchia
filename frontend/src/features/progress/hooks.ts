import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { completeReview, fetchDashboard, fetchReview, startReview, type ReviewState } from "@/lib/api/progress";

export const progressKeys = {
  dashboard: ["dashboard"] as const,
  review: ["review"] as const,
};

export function useDashboard() {
  return useQuery({ queryKey: progressKeys.dashboard, queryFn: ({ signal }) => fetchDashboard(signal) });
}

const generating = (state: ReviewState | undefined) =>
  state?.current?.extras === "queued" || state?.current?.extras === "running";

export function useReview() {
  return useQuery({
    queryKey: progressKeys.review,
    queryFn: ({ signal }) => fetchReview(signal),
    // Poll while the local LLM is writing extra exercises for this set.
    refetchInterval: (query) => (generating(query.state.data) ? 5000 : false),
  });
}

export function useStartReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: startReview,
    onSuccess: (created) => {
      queryClient.setQueryData<ReviewState>(progressKeys.review, (old) => ({
        weak_topics: old?.weak_topics ?? [],
        current: created,
      }));
      void queryClient.invalidateQueries({ queryKey: progressKeys.dashboard });
    },
  });
}

export function useCompleteReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: completeReview,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: progressKeys.review });
      void queryClient.invalidateQueries({ queryKey: progressKeys.dashboard });
    },
  });
}
