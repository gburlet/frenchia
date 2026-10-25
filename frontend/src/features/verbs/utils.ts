import { ApiError } from "@/lib/api/client";
import type { DrillMode } from "@/lib/api/verbs";

/** Lowercase and strip diacritics for accent-insensitive search. */
export function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

export interface DrillParams {
  set?: string | null;
  verbs?: string[];
  tenses: string[];
  mode?: DrillMode;
  count?: number;
}

export function drillUrl({ set, verbs, tenses, mode = "mixed", count = 10 }: DrillParams): string {
  const p = new URLSearchParams();
  if (verbs && verbs.length > 0) p.set("verbs", verbs.join(","));
  else if (set) p.set("set", set);
  p.set("tenses", tenses.join(","));
  p.set("mode", mode);
  p.set("count", String(count));
  return `/practice/verbs/drill?${p.toString()}`;
}

/** Friendly text for an API error; 400 bodies carry `detail` as a list of strings. */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body;
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (Array.isArray(detail)) return detail.map(String).join(" ");
      if (typeof detail === "string") return detail;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

/** Marks which characters of `text` are not part of the longest common subsequence with `other`. */
export function diffMask(text: string, other: string): boolean[] {
  const a = Array.from(text.toLowerCase());
  const b = Array.from(other.toLowerCase());
  const dp: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      dp[i]![j] = a[i] === b[j] ? dp[i + 1]![j + 1]! + 1 : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);
    }
  }
  const mask = new Array<boolean>(a.length).fill(true);
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      mask[i] = false;
      i++;
      j++;
    } else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) i++;
    else j++;
  }
  return mask;
}
