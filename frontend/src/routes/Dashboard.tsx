import { useMe } from "@/features/auth/hooks";
import { HealthCard } from "@/features/health/HealthCard";

export function Dashboard() {
  const me = useMe();
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-3xl">Bonjour, {me.data?.username}</h1>
      <div className="grid gap-6 md:grid-cols-2">
        <HealthCard />
      </div>
    </div>
  );
}
