import { useState, type FormEvent } from "react";
import { Languages, Loader2 } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { FullPageLoader } from "@/components/FullPageLoader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { useLogin, useMe } from "./hooks";

interface LocationState {
  from?: { pathname?: string; search?: string; hash?: string };
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.status >= 500 ? "The server had a problem. Please try again." : error.detail;
  }
  return "Unable to reach the server. Please try again.";
}

export function LoginPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const me = useMe();
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const from = (location.state as LocationState | null)?.from;
  const target = from?.pathname ? `${from.pathname}${from.search ?? ""}${from.hash ?? ""}` : "/";

  if (me.isPending) return <FullPageLoader />;
  if (me.data) return <Navigate to={target} replace />;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    login.mutate(
      { username, password },
      { onSuccess: () => void navigate(target, { replace: true }) },
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-page px-4 py-12">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="mb-2 flex items-center gap-2 text-purple">
            <Languages className="size-6" aria-hidden="true" />
            <span className="font-heading text-lg font-extrabold text-heading">Frenchia</span>
          </div>
          <CardTitle>Connexion</CardTitle>
          <CardDescription>Sign in to continue learning.</CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" aria-busy={login.isPending}>
          {login.isError && (
            <Alert>
              <AlertDescription>{errorMessage(login.error)}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              name="username"
              autoComplete="username"
              required
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={login.isPending}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={login.isPending}
            />
          </div>
          <Button type="submit" fullWidth disabled={login.isPending}>
            {login.isPending && (
              <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            )}
            {login.isPending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
