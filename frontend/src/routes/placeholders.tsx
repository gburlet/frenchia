import { Badge } from "@/components/ui/badge";

function ComingSoon({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col items-start gap-3">
      <h1 className="text-3xl">{title}</h1>
      <p className="text-detail">{description}</p>
      <Badge variant="neutral">Coming soon</Badge>
    </div>
  );
}

export const ProgressPage = () => (
  <ComingSoon title="Progress" description="Track how far you have come." />
);
