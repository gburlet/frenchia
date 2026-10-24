import { Navigate, Outlet, useLocation } from "react-router";
import { FullPageLoader } from "@/components/FullPageLoader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useMe } from "./hooks";

export function RequireAuth() {
  const location = useLocation();
  const me = useMe();

  if (me.isPending) return <FullPageLoader />;

  if (me.isError) {
    return (
      <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-4">
        <Alert>
          <AlertDescription>Unable to reach the server. Please try again.</AlertDescription>
        </Alert>
        <Button variant="ghost" onClick={() => void me.refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (!me.data) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
