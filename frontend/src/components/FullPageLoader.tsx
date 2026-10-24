import { Loader2 } from "lucide-react";

export function FullPageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-screen items-center justify-center bg-page text-muted"
    >
      <Loader2 className="size-6 animate-spin motion-reduce:animate-none" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
