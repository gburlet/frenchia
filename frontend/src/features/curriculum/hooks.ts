import { useQuery } from "@tanstack/react-query";
import { fetchCurriculum } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import type { Curriculum, CurriculumLesson } from "@/lib/api/types";

export function useCurriculum() {
  return useQuery({
    queryKey: queryKeys.curriculum,
    queryFn: ({ signal }) => fetchCurriculum(signal),
    staleTime: 30_000,
  });
}

/** First in-progress lesson, else the first published lesson not yet started. */
export function findContinueLesson(
  curriculum: Curriculum,
): { lesson: CurriculumLesson; level: string; inProgress: boolean } | null {
  let firstNew: { lesson: CurriculumLesson; level: string; inProgress: boolean } | null = null;
  for (const level of curriculum.levels) {
    for (const unit of level.units) {
      for (const lesson of unit.lessons) {
        if (!lesson.published) continue;
        if (lesson.progress.status === "in_progress") {
          return { lesson, level: level.level, inProgress: true };
        }
        if (!firstNew && lesson.progress.status === "not_started") {
          firstNew = { lesson, level: level.level, inProgress: false };
        }
      }
    }
  }
  return firstNew;
}

/** Level of the furthest completed lesson in curriculum order, or null if none is completed. */
export function findLastCompletedLevel(curriculum: Curriculum): string | null {
  let found: string | null = null;
  for (const level of curriculum.levels) {
    for (const unit of level.units) {
      if (unit.lessons.some((lesson) => lesson.progress.status === "completed")) found = level.level;
    }
  }
  return found;
}
