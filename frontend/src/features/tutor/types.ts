export interface TutorContextRef {
  lesson_id?: string;
  exercise_revision_id?: number;
  attempt_id?: number;
}

export interface TutorContextInfo {
  ref: TutorContextRef;
  /** Short human label; empty when there is no context. */
  label: string;
}

export type TutorMessageStatus = "streaming" | "complete" | "stopped" | "error";

export interface ChatMessage {
  kind: "message";
  localId: string;
  serverId?: number;
  role: "user" | "assistant";
  content: string;
  status: TutorMessageStatus;
  error?: string;
  /** Used to resend when the failure happened before the server created the reply. */
  retryContent?: string;
}
export interface ChatDivider {
  kind: "divider";
  localId: string;
  label: string;
}
export type ChatItem = ChatMessage | ChatDivider;

export type ThreadId = string | number;

export interface ThreadDetail {
  id: ThreadId;
  title: string;
  context: TutorContextRef;
  messages: {
    id: number;
    role: "user" | "assistant";
    content: string;
    status: "complete" | "stopped" | "error";
    created_at: string;
  }[];
}

export function contextKey(ref: TutorContextRef): string {
  return JSON.stringify([ref.lesson_id ?? null, ref.exercise_revision_id ?? null, ref.attempt_id ?? null]);
}
