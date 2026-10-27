import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SpeakButton } from "@/features/audio/SpeakButton";
import { splitSentences, stripBold, withArticle } from "@/lib/sentences";
import type {
  ExamplesSection,
  ExplanationSection,
  LessonSection,
  ReadingSection,
  RegionalNoteSection,
  TableSection,
  VocabItem,
  VocabularySection,
} from "@/lib/api/types";
import { Markdown } from "./Markdown";
import { BoldText } from "./BoldText";

const QcPill = () => (
  <Badge variant="teal" title="Québec" className="px-2 py-0 text-[0.7rem]">
    QC
  </Badge>
);

function SectionShell({
  id,
  heading,
  children,
  accent,
}: {
  id: string;
  heading: string;
  children: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <section
      id={`section-${id}`}
      aria-labelledby={`h-${id}`}
      className={
        accent ? "rounded-card border-l-4 border-teal bg-surface p-5" : ""
      }
    >
      <h2 id={`h-${id}`} className="mb-3 text-2xl">
        {heading}
      </h2>
      {children}
    </section>
  );
}

function Explanation({ section }: { section: ExplanationSection }) {
  return (
    <SectionShell id={section.id} heading={section.heading}>
      <Markdown>{section.body}</Markdown>
    </SectionShell>
  );
}

function Examples({ section }: { section: ExamplesSection }) {
  return (
    <SectionShell id={section.id} heading={section.heading}>
      <ul className="flex flex-col divide-y divide-line rounded-card bg-surface">
        {section.examples.map((ex, i) => (
          <li key={i} className="flex items-start gap-2 px-4 py-3">
            <div className="min-w-0 flex-1">
              <p
                lang="fr"
                className="flex flex-wrap items-center gap-2 font-bold text-heading"
              >
                <BoldText text={ex.fr} />
                {ex.region === "qc" && <QcPill />}
              </p>
              <p className="text-body">{ex.en}</p>
              {ex.note && (
                <p className="mt-0.5 text-sm text-muted">{ex.note}</p>
              )}
            </div>
            <SpeakButton text={ex.fr} label={`Écouter : ${stripBold(ex.fr)}`} />
          </li>
        ))}
      </ul>
    </SectionShell>
  );
}

function Table({ section }: { section: TableSection }) {
  return (
    <SectionShell id={section.id} heading={section.heading}>
      <div className="overflow-x-auto rounded-card bg-surface">
        <table className="w-full border-collapse text-left text-sm">
          {section.caption && (
            <caption className="px-4 py-2 text-left text-sm text-detail">
              {section.caption}
            </caption>
          )}
          <thead>
            <tr>
              {section.columns.map((c) => (
                <th
                  key={c}
                  scope="col"
                  className="border-b border-line px-4 py-2 text-heading"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {section.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) =>
                  j === 0 ? (
                    <th
                      key={j}
                      scope="row"
                      className="border-b border-line px-4 py-2 text-left font-bold text-heading"
                    >
                      {cell}
                    </th>
                  ) : (
                    <td key={j} className="border-b border-line px-4 py-2">
                      {cell}
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionShell>
  );
}

function VocabTable({ items }: { items: VocabItem[] }) {
  return (
    <div className="overflow-x-auto rounded-card bg-surface">
      <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
        <thead>
          <tr>
            <th
              scope="col"
              className="border-b border-line px-4 py-2 text-heading"
            >
              Français
            </th>
            <th
              scope="col"
              className="border-b border-line px-4 py-2 text-heading"
            >
              English
            </th>
            <th
              scope="col"
              className="border-b border-line px-4 py-2 text-heading"
            >
              Example
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => {
            const display = withArticle(
              item.fr,
              item.gender,
              item.pos === "noun",
            );
            return (
              <tr key={i} className="align-top">
                <td className="border-b border-line px-4 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span lang="fr" className="font-bold text-heading">
                      {display}
                    </span>
                    <SpeakButton
                      text={display}
                      label={`Écouter : ${display}`}
                    />
                    {item.gender && (
                      <Badge
                        variant="outline"
                        title={item.gender === "m" ? "masculin" : "féminin"}
                        className="px-2 py-0 text-[0.7rem]"
                      >
                        {item.gender === "m" ? "m." : "f."}
                      </Badge>
                    )}
                    {item.region === "qc" && <QcPill />}
                    {item.formality === "familiar" && (
                      <Badge
                        variant="warning"
                        className="px-2 py-0 text-[0.7rem]"
                      >
                        familiar
                      </Badge>
                    )}
                    {item.formality === "formal" && (
                      <Badge
                        variant="outline"
                        className="px-2 py-0 text-[0.7rem]"
                      >
                        formal
                      </Badge>
                    )}
                  </div>
                </td>
                <td className="border-b border-line px-4 py-2">{item.en}</td>
                <td className="border-b border-line px-4 py-2">
                  {item.example_fr && (
                    <div className="flex items-start gap-1">
                      <div>
                        <p lang="fr" className="text-heading">
                          <BoldText text={item.example_fr} />
                        </p>
                        {item.example_en && (
                          <p className="text-muted">{item.example_en}</p>
                        )}
                      </div>
                      <SpeakButton
                        text={item.example_fr}
                        label={`Écouter l’exemple : ${stripBold(item.example_fr)}`}
                      />
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Vocabulary({ section }: { section: VocabularySection }) {
  return (
    <SectionShell id={section.id} heading={section.heading}>
      <VocabTable items={section.items} />
    </SectionShell>
  );
}

function Reading({ section }: { section: ReadingSection }) {
  const [showEn, setShowEn] = useState(false);
  const sentences = splitSentences(section.passage_fr);
  const glossary = section.glossary ?? [];
  return (
    <SectionShell id={section.id} heading={section.title}>
      <div className="rounded-card bg-surface p-5">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-1 text-sm text-detail">
            <SpeakButton text={section.passage_fr} label="Play all" />
            Play all
          </span>
          <Button
            type="button"
            variant="ghost"
            aria-expanded={showEn}
            onClick={() => setShowEn((v) => !v)}
          >
            {showEn ? "Hide translation" : "Show translation"}
          </Button>
        </div>
        <div
          lang="fr"
          className="max-w-[70ch] text-lg leading-relaxed text-heading"
        >
          {sentences.map((s, i) => (
            <span key={i} className="mr-1 inline">
              <BoldText text={s} />
              <SpeakButton
                text={s}
                className="size-7 align-middle [&_svg]:size-4"
                label={`Écouter la phrase ${i + 1}`}
              />{" "}
            </span>
          ))}
        </div>
        {showEn && (
          <p className="mt-4 max-w-[70ch] border-t border-line pt-3 text-body">
            {section.translation_en}
          </p>
        )}
      </div>
      {glossary.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-lg">Glossary</h3>
          <VocabTable items={glossary} />
        </div>
      )}
    </SectionShell>
  );
}

function RegionalNote({ section }: { section: RegionalNoteSection }) {
  const variants = section.variants ?? [];
  return (
    <SectionShell id={section.id} heading={section.heading} accent>
      <Markdown>{section.body}</Markdown>
      {variants.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[30rem] border-collapse text-left text-sm">
            <caption className="sr-only">Regional variants</caption>
            <thead>
              <tr>
                <th
                  scope="col"
                  className="border-b border-line px-3 py-2 text-heading"
                >
                  Québec
                </th>
                <th
                  scope="col"
                  className="border-b border-line px-3 py-2 text-heading"
                >
                  France
                </th>
                <th
                  scope="col"
                  className="border-b border-line px-3 py-2 text-heading"
                >
                  English
                </th>
              </tr>
            </thead>
            <tbody>
              {variants.map((v, i) => (
                <tr key={i}>
                  <td className="border-b border-line px-3 py-2 text-heading">
                    <span lang="fr">{v.qc}</span> <SpeakButton text={v.qc} />
                  </td>
                  <td className="border-b border-line px-3 py-2 text-heading">
                    <span lang="fr">{v.fr}</span> <SpeakButton text={v.fr} />
                  </td>
                  <td className="border-b border-line px-3 py-2">{v.en}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionShell>
  );
}

export function SectionView({ section }: { section: LessonSection }) {
  switch (section.type) {
    case "explanation":
      return <Explanation section={section} />;
    case "examples":
      return <Examples section={section} />;
    case "table":
      return <Table section={section} />;
    case "vocabulary":
      return <Vocabulary section={section} />;
    case "reading":
      return <Reading section={section} />;
    case "regional_note":
      return <RegionalNote section={section} />;
    default:
      return null;
  }
}
