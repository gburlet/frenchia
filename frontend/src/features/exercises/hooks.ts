import { useMutation, useQueryClient } from "@tanstack/react-query";
import { disputeAttempt, regradeAttempt, submitAttempt } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import type { AttemptRequest } from "@/lib/api/types";

export function useSubmitAttempt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ revisionId, body }: { revisionId: number; body: AttemptRequest }) =>
      submitAttempt(revisionId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.curriculum }),
  });
}

export function useRegrade() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (attemptId: number) => regradeAttempt(attemptId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.curriculum }),
  });
}

export function useDispute() {
  return useMutation({
    mutationFn: ({ attemptId, comment }: { attemptId: number; comment?: string }) =>
      disputeAttempt(attemptId, comment),
  });
}
