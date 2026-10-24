import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SpeakButton } from "./SpeakButton";

const SAMPLE = "Salut ! On va-tu souper au resto en fin de semaine ?";

/** Lets the learner confirm French speech works, at normal and slow speed. */
export function VoiceCheckCard() {
  return (
    <Card aria-labelledby="voice-check-title" role="region">
      <CardHeader>
        <CardTitle id="voice-check-title">Voice check</CardTitle>
        <CardDescription>French speech is generated locally by Kokoro.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p lang="fr-CA" className="text-detail">
          {SAMPLE}
        </p>
        <div className="flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1">
            <SpeakButton text={SAMPLE} label="Écouter à vitesse normale" /> Normal
          </span>
          <span className="flex items-center gap-1">
            <SpeakButton text={SAMPLE} speed={0.75} label="Écouter lentement" /> Lent
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
