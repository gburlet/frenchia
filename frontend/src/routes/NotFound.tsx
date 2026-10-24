import { Link } from "react-router";
import { Button } from "@/components/ui/button";

export function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-page px-4 text-center">
      <h1 className="text-4xl">404</h1>
      <p>Cette page est introuvable. This page does not exist.</p>
      <Button asChild>
        <Link to="/">Back to dashboard</Link>
      </Button>
    </main>
  );
}
