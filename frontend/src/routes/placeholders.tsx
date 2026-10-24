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

export const CurriculumPage = () => (
  <ComingSoon title="Curriculum" description="Your learning path, unit by unit." />
);
export const TranslatePage = () => (
  <ComingSoon title="Translate" description="Practise translating between English and Québec French." />
);
export const VerbsPage = () => (
  <ComingSoon title="Verbs" description="Drill conjugations until they feel natural." />
);
export const VocabPage = () => (
  <ComingSoon title="Vocabulary" description="Build and review your vocabulary." />
);
export const ProgressPage = () => (
  <ComingSoon title="Progress" description="Track how far you have come." />
);
