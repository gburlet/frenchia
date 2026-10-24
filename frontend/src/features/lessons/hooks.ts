import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchLesson, updateProgress } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import type { Lesson, ProgressUpdate } from "@/lib/api/types";

export function useLesson(id: string) {
  return useQuery({
    queryKey: queryKeys.lesson(id),
    queryFn: ({ signal }) => fetchLesson(id, signal),
    retry: false,
  });
}

export function useUpdateProgress(lessonId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProgressUpdate) => updateProgress(lessonId, body),
    onSuccess: (progress) => {
      queryClient.setQueryData<Lesson>(queryKeys.lesson(lessonId), (old) =>
        old ? { ...old, progress } : old,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.curriculum });
    },
  });
}
