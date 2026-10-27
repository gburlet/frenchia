import { describe, expect, it } from "vitest";
import { splitSentences, stripBold, withArticle } from "./sentences";

describe("splitSentences", () => {
  it("splits after . ! ? … followed by whitespace", () => {
    expect(splitSentences("Il pleut. Il neige! Tu viens? Peut-être… Oui.")).toEqual([
      "Il pleut.",
      "Il neige!",
      "Tu viens?",
      "Peut-être…",
      "Oui.",
    ]);
  });
  it("handles French spacing before ? and ! (incl. narrow no-break spaces)", () => {
    expect(splitSentences("Tu viens ? Oui\u202f! Super\u00a0! Allons-y.")).toEqual([
      "Tu viens ?",
      "Oui\u202f!",
      "Super\u00a0!",
      "Allons-y.",
    ]);
  });
  it("keeps guillemets with their sentence", () => {
    expect(splitSentences("Elle dit : « Bonjour ! » Puis elle part.")).toEqual([
      "Elle dit : « Bonjour ! »",
      "Puis elle part.",
    ]);
    expect(splitSentences("« Viens ici ! » dit-il. Il rit.")).toEqual(["« Viens ici ! » dit-il.", "Il rit."]);
    expect(splitSentences("« Tu viens\u202f? »\u00a0demande Luc.")).toEqual(["« Tu viens\u202f? »\u00a0demande Luc."]);
  });
  it("does not split on abbreviations", () => {
    expect(splitSentences("M. Tremblay habite ici. Mme Roy aussi.")).toEqual([
      "M. Tremblay habite ici.",
      "Mme Roy aussi.",
    ]);
    expect(splitSentences("On dit, p. ex. bonjour. Voilà.")).toEqual(["On dit, p. ex. bonjour.", "Voilà."]);
    expect(splitSentences("J. Roy arrive. Bien.")).toEqual(["J. Roy arrive.", "Bien."]);
  });
  it("does not split inside numbers or ellipsis runs", () => {
    expect(splitSentences("Il coûte 3.50 $. Cher...  Non.")).toEqual(["Il coûte 3.50 $.", "Cher...", "Non."]);
  });
  it("splits on paragraph breaks and handles empty input", () => {
    expect(splitSentences("Un\n\nDeux")).toEqual(["Un", "Deux"]);
    expect(splitSentences("  ")).toEqual([]);
  });
});

describe("withArticle", () => {
  it("adds un/une or l’ for nouns only", () => {
    expect(withArticle("livre", "m", true)).toBe("un livre");
    expect(withArticle("maison", "f", true)).toBe("une maison");
    expect(withArticle("école", "f", true)).toBe("l’école");
    expect(withArticle("manger", null, false)).toBe("manger");
  });
  it("leaves proper nouns without an article", () => {
    expect(withArticle("Vieux-Québec", "m", true)).toBe("Vieux-Québec");
  });
});

describe("stripBold", () => {
  it("removes the ** markers that highlight a taught form", () => {
    expect(stripBold("Je **mange** une pomme.")).toBe("Je mange une pomme.");
  });
});
