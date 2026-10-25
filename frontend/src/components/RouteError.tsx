import { isRouteErrorResponse, Link, useRouteError } from "react-router";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function describe(error: unknown): { title: string; detail: string } {
  if (isRouteErrorResponse(error)) {
    return { title: error.status === 404 ? "Page not found" : `Error ${error.status}`, detail: error.statusText };
  }
  const message = error instanceof Error ? error.message : String(error);
  // After a rebuild the browser may ask for a page chunk that no longer exists.
  if (/dynamically imported module|Importing a module script failed|error loading dynamically/i.test(message)) {
    return { title: "Frenchia was updated", detail: "Reload the page to get the new version." };
  }
  return { title: "Something went wrong", detail: message };
}

/** Shown instead of a page that crashed or failed to load; the header and nav stay usable. */
export function RouteError({ fullPage = false }: { fullPage?: boolean }) {
  const { title, detail } = describe(useRouteError());
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-start gap-3", fullPage && "min-h-screen justify-center bg-page p-8")}
    >
      <h1 className="text-3xl">{title}</h1>
      {detail && <p className="max-w-prose break-words text-detail">{detail}</p>}
      <div className="flex gap-3">
        <Button variant="secondary" onClick={() => window.location.reload()}>
          Reload
        </Button>
        <Link to="/" className="self-center text-teal underline">
          Back to the dashboard
        </Link>
      </div>
    </div>
  );
}
