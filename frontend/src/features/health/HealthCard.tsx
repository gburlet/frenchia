import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchHealth } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";

const SERVICE_LABELS: Record<string, string> = {
  database: "Database",
  llm: "Language model",
  tts: "Speech (TTS)",
};

function variantFor(status: string) {
  if (status === "ok") return "success" as const;
  if (status === "error") return "failure" as const;
  return "blocked" as const;
}

export function HealthCard() {
  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => fetchHealth(signal),
    refetchInterval: 15_000,
    retry: false,
  });

  return (
    <Card aria-labelledby="system-status-title" role="region">
      <CardHeader>
        <CardTitle id="system-status-title">System status</CardTitle>
        <CardDescription>Refreshes every 15 seconds.</CardDescription>
      </CardHeader>
      <CardContent>
        {health.isPending && <p role="status">Checking services…</p>}
        {health.isError && (
          <Alert>
            <AlertDescription>Unable to load system status.</AlertDescription>
          </Alert>
        )}
        {health.data && (
          <div className="flex flex-col gap-3">
            <ul className="flex flex-col gap-2">
              <li className="flex items-center justify-between gap-4">
                <span className="text-detail">Overall</span>
                <Badge variant={health.data.status === "ok" ? "success" : "blocked"}>
                  {health.data.status}
                </Badge>
              </li>
              {Object.entries(health.data.services).map(([name, status]) => (
                <li key={name} className="flex items-center justify-between gap-4">
                  <span className="text-detail">{SERVICE_LABELS[name] ?? name}</span>
                  <Badge variant={variantFor(status)}>{status}</Badge>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted">Version {health.data.version}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
