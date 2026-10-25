import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { mockFetch, staffUser } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

const index = {
  tenses: [
    { key: "indicatif.present", label: "Présent", label_en: "Present", level: "A1", mood: "Indicatif", compound: false, drill: true },
    { key: "indicatif.passe_compose", label: "Passé composé", label_en: "Perfect", level: "A1", mood: "Indicatif", compound: true, drill: true },
    { key: "indicatif.imparfait", label: "Imparfait", label_en: "Imperfect", level: "A2", mood: "Indicatif", compound: false, drill: true },
    { key: "indicatif.passe_simple", label: "Passé simple", label_en: "Past historic", level: "B2", mood: "Indicatif", compound: false, drill: false },
  ],
  sets: [
    { id: "essentiels", title: "Les essentiels", title_en: "The essentials", level: "A1", description: "Core verbs.", verbs: ["être", "avoir"], tenses: ["indicatif.present", "indicatif.passe_compose"] },
    { id: "mouvement", title: "Le mouvement", title_en: "Movement", level: "A2", description: "Verbs of motion.", verbs: ["aller", "partir", "venir"], tenses: ["indicatif.imparfait"] },
  ],
  verbs: [
    { infinitive: "aller", slug: "aller", en: "to go", group: 3, auxiliary: "être", pronominal: false, sentences: 3, sets: ["mouvement"] },
    { infinitive: "se lever", slug: "se-lever", en: null, group: 1, auxiliary: "être", pronominal: true, sentences: 0, sets: [] },
    { infinitive: "être", slug: "etre", en: "to be", group: 3, auxiliary: "avoir", pronominal: false, sentences: 2, sets: ["essentiels"] },
  ],
};
const progress = {
  attempts: 10,
  correct: 8,
  verbs_practiced: 3,
  weak_spots: [{ infinitive: "aller", slug: "aller", tense: "indicatif.passe_compose", tense_label: "Passé composé", attempts: 3, ewma: 0.4 }],
};

const formItem = {
  infinitive: "aller", slug: "aller", en: "to go", tense: "indicatif.passe_compose", tense_label: "Passé composé",
  person: "je", subject: "je", mode: "form", sentence: null,
};
const sentence = { bank: "partir", version: 2, index: 0, before: "Hier soir, ma blonde ", after: " tard.", en: "Last night my girlfriend left late.", region: "qc" };
const ctxItem = {
  infinitive: "partir", slug: "partir", en: "to leave", tense: "indicatif.passe_compose", tense_label: "Passé composé",
  person: "il", subject: "il/elle/on", mode: "context", sentence,
};
const okResult = { result: "correct", correct: true, expected: "je suis allé", accepted: [], diagnosis: "", message: "", said: "je suis allé" };
const badResult = { result: "incorrect", correct: false, expected: "est partie", accepted: [], diagnosis: "agreement", message: "partir takes être.", said: "Hier soir, ma blonde est partie tard." };

const base = { "GET /api/auth/me": { body: staffUser } };

describe("Verb Station", { timeout: 15000 }, () => {
  beforeEach(() => {
    document.cookie = "csrftoken=tok; path=/";
  });

  it("lists sets and builds the drill URL", async () => {
    mockFetch({ ...base, "GET /api/verbs": { body: index }, "GET /api/verbs/progress": { body: progress } });
    const user = userEvent.setup();
    const { router } = renderApp("/practice/verbs");
    expect(await screen.findByRole("button", { name: /Le mouvement/ }, { timeout: 5000 })).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: /Le mouvement/ })).getByText("3 verbs")).toBeInTheDocument();
    expect(await screen.findByText("Weak spots")).toBeInTheDocument();
    // default: first set with its tenses; passé simple not offered
    expect(screen.getByLabelText("Présent")).toBeChecked();
    expect(screen.queryByLabelText("Passé simple")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Le mouvement/ }));
    expect(screen.getByLabelText("Imparfait")).toBeChecked();
    expect(screen.getByLabelText("Présent")).not.toBeChecked();
    await user.click(screen.getByLabelText("Présent"));
    await user.selectOptions(screen.getByLabelText("Mode"), "form");
    await user.selectOptions(screen.getByLabelText("Questions"), "20");
    await user.click(screen.getByRole("button", { name: "Start drill" }));
    await waitFor(() =>
      expect(router.state.location.pathname + router.state.location.search).toBe(
        "/practice/verbs/drill?set=mouvement&tenses=indicatif.imparfait%2Cindicatif.present&mode=form&count=20",
      ),
    );
  });

  it("filters the browser accent-insensitively", async () => {
    mockFetch({ ...base, "GET /api/verbs": { body: index }, "GET /api/verbs/progress": { body: progress } });
    const user = userEvent.setup();
    renderApp("/practice/verbs");
    await screen.findByRole("button", { name: /Le mouvement/ }, { timeout: 5000 });
    const list = screen.getByRole("list", { name: "Verbs" });
    expect(within(list).getAllByRole("link")).toHaveLength(3);
    await user.type(screen.getByLabelText("Search verbs"), "etre");
    expect(within(list).getAllByRole("link")).toHaveLength(1);
    expect(within(list).getByRole("link")).toHaveAttribute("href", "/practice/verbs/etre");
  });

  it("drill: form item posts the payload, shows feedback, Enter goes next, summary lists misses", async () => {
    const posted: unknown[] = [];
    mockFetch({
      ...base,
      "POST /api/verbs/drills": { body: { items: [formItem, ctxItem] } },
      "POST /api/verbs/answers": (init) => {
        const body = JSON.parse(String(init?.body)) as { answers: { mode: string }[] };
        posted.push(body);
        return { body: { results: [body.answers[0]!.mode === "form" ? okResult : badResult] } };
      },
    });
    const user = userEvent.setup();
    renderApp("/practice/verbs/drill?verbs=aller,partir&tenses=indicatif.passe_compose&mode=mixed&count=2");
    const input = await screen.findByRole("textbox", { name: "Your answer" });
    expect(screen.getByText("(to go)")).toBeInTheDocument();
    await waitFor(() => expect(input).toHaveFocus());
    await user.type(input, "suis allé{Enter}");
    expect(await screen.findByText("Correct!")).toBeInTheDocument();
    const first = posted[0] as { answers: Record<string, unknown>[] };
    expect(first.answers[0]).toMatchObject({
      infinitive: "aller", tense: "indicatif.passe_compose", person: "je", answer: "suis allé", mode: "form",
    });
    expect(typeof first.answers[0]!.time_spent_ms).toBe("number");
    expect(first.answers[0]!.sentence).toBeUndefined();

    await user.keyboard("{Enter}");
    // context item: before / input / after, translation underneath
    expect(await screen.findByText(/Hier soir, ma blonde/)).toBeInTheDocument();
    expect(screen.getByText("tard.")).toBeInTheDocument();
    expect(screen.getByText("Last night my girlfriend left late.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Your answer" }), "a parti{Enter}");
    expect(await screen.findByText("Incorrect")).toBeInTheDocument();
    const second = posted[1] as { answers: Record<string, unknown>[] };
    expect(second.answers[0]).toMatchObject({ mode: "context", sentence: { bank: "partir", version: 2, index: 0 } });

    await user.keyboard("{Enter}");
    expect(await screen.findByTestId("score")).toHaveTextContent("1 / 2");
    const misses = screen.getByRole("region", { name: "Misses" });
    expect(within(misses).getByText("a parti")).toBeInTheDocument();
    expect(within(misses).getByText("est partie")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Practice my mistakes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New drill" })).toBeInTheDocument();
  });

  it("drill: friendly message on 400", async () => {
    mockFetch({
      ...base,
      "POST /api/verbs/drills": { status: 400, body: { detail: ["no context sentences for these verbs and tenses yet"] } },
    });
    renderApp("/practice/verbs/drill?verbs=aller&tenses=indicatif.present&mode=context&count=5");
    expect(await screen.findByText(/no context sentences for these verbs and tenses yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the Verb Station" })).toHaveAttribute("href", "/practice/verbs");
  });

  it("detail page renders tables and the tense quiz posts six answers", async () => {
    const persons = ["je", "tu", "il", "nous", "vous", "ils"];
    const detail = {
      ...index.verbs[0],
      note: "Takes être.",
      participle_past: "allé",
      participle_present: "allant",
      table: [
        { tense: "indicatif.present", label: "Présent", label_en: "Present", mood: "Indicatif", level: "A1",
          rows: persons.map((p) => ({ person: p, form: `f-${p}`, variants: p === "tu" ? ["alt-tu"] : [], said: `${p} f` })) },
      ],
      examples: [{ tense: "indicatif.passe_compose", tense_label: "Passé composé", person: "il", fr: "Ma blonde est allée au dépanneur.", en: "My girlfriend went.", form: "est allée", region: "qc" }],
      mastery: [{ tense: "indicatif.present", attempts: 4, ewma: 0.8 }],
    };
    let posted: { answers: { person: string; mode: string; answer: string }[] } | null = null;
    mockFetch({
      ...base,
      "GET /api/verbs/aller": { body: detail },
      "POST /api/verbs/answers": (init) => {
        posted = JSON.parse(String(init?.body));
        return {
          body: {
            results: persons.map((p) => ({
              result: p === "je" ? "correct" : "incorrect", correct: p === "je", expected: `exp-${p}`,
              accepted: [], diagnosis: "", message: p === "tu" ? "Watch the ending." : "", said: p,
            })),
          },
        };
      },
    });
    const user = userEvent.setup();
    renderApp("/practice/verbs/aller");
    expect(await screen.findByRole("heading", { name: "aller" })).toBeInTheDocument();
    expect(screen.getByText("also: alt-tu")).toBeInTheDocument();
    expect(screen.getByText("QC")).toBeInTheDocument();
    expect(screen.getByText("est allée")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: /Mastery of Présent/ })).toHaveAttribute("aria-valuenow", "80");
    expect(screen.getByRole("link", { name: "Drill this verb" })).toHaveAttribute(
      "href",
      "/practice/verbs/drill?verbs=aller&tenses=indicatif.present&mode=mixed&count=10",
    );

    await user.click(screen.getByRole("button", { name: /Quiz this tense/ }));
    await user.type(screen.getByLabelText("je"), "vais");
    await user.click(screen.getByRole("button", { name: "Check" }));
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.answers).toHaveLength(6);
    expect(posted!.answers.every((a) => a.mode === "table")).toBe(true);
    expect(posted!.answers[0]).toMatchObject({ person: "je", answer: "vais" });
    expect(await screen.findByText("1 / 6 correct")).toBeInTheDocument();
    expect(screen.getByTestId("quiz-result-tu")).toHaveTextContent("expected exp-tu");
    expect(screen.getByTestId("quiz-result-tu")).toHaveTextContent("Watch the ending.");
  });
});
