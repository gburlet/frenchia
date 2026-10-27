import { describe, expect, it } from "vitest";
import { cleanHeading, inlineParts } from "./inline";

describe("inlineParts", () => {
  it("reads **bold** and *italic*", () => {
    expect(inlineParts("Use *très* with **beau**.")).toEqual([
      { text: "Use ", bold: false, italic: false },
      { text: "très", bold: false, italic: true },
      { text: " with ", bold: false, italic: false },
      { text: "beau", bold: true, italic: false },
      { text: ".", bold: false, italic: false },
    ]);
  });

  it("merges two bold runs written back to back", () => {
    expect(inlineParts("**je parler****ai**")).toEqual([{ text: "je parlerai", bold: true, italic: false }]);
  });

  it("drops asterisks it cannot pair instead of showing them", () => {
    const text = inlineParts("*Je doute **qu'**il **ait fini** son travail.*")
      .map((p) => p.text)
      .join("");
    expect(text).toBe("Je doute qu'il ait fini son travail.");
  });
});

describe("cleanHeading", () => {
  it("removes Markdown heading marks from a heading field", () => {
    expect(cleanHeading("## The Past Conditional")).toBe("The Past Conditional");
  });
});
