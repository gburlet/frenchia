import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { cleanMarkdown } from "./cleanMarkdown";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("turns HTML breaks and stray symbols into line breaks and drops comments", () => {
    expect(cleanMarkdown("a<br>b<br/>c⟩⟩⟩d⏎e<!-- x -->")).toBe("a\nb\nc\nd\ne");
    expect(cleanMarkdown("x\n\n| A | B |\n\n|---|---|\n\n| 1 | 2 |")).toBe(
      "x\n\n| A | B |\n| --- | --- |\n| 1 | 2 |",
    );
  });

  it("restores the line breaks of a body written on one line", () => {
    const flat = "### Forms  Intro.  | Verb | Form | |---|---| | parler | parlé |  - a";
    expect(cleanMarkdown(flat)).toBe(
      "### Forms\n\nIntro.\n\n| Verb | Form |\n| --- | --- |\n| parler | parlé |\n\n- a",
    );
    render(<Markdown>{flat}</Markdown>);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Forms" })).toBeInTheDocument();
  });

  it("renders a table whose rows were separated by <br>", () => {
    render(<Markdown>{"| Verbe | Forme |<br>|---|---|<br>| parler | parlé |"}</Markdown>);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByText(/<br>/)).not.toBeInTheDocument();
  });
});

describe("generated Markdown that doesn't parse cleanly", () => {
  it("breaks a body flattened onto one line despite newlines elsewhere", () => {
    const body = "Intro line.\nIt means *will have*.  ## Formation  ### 1. Auxiliary  - avoir: aurai  - être: serai";
    const { container } = render(<Markdown>{body}</Markdown>);
    expect(container.textContent).not.toContain("##");
    expect(container.querySelectorAll("li")).toHaveLength(2);
  });

  it("shows no asterisks when emphasis is nested around an apostrophe", () => {
    const { container } = render(<Markdown>{"Example: *Je doute **qu'**il **ait fini** son travail.*"}</Markdown>);
    expect(container.textContent).toBe("Example: Je doute qu'il ait fini son travail.");
    expect([...container.querySelectorAll("strong")].map((s) => s.textContent)).toContain("ait fini");
  });

  it("renders a leftover **bold** Markdown could not close", () => {
    const { container } = render(<Markdown>{"Il faut **qu'**il vienne."}</Markdown>);
    expect(container.textContent).toBe("Il faut qu'il vienne.");
    expect(container.querySelector("strong")?.textContent).toBe("qu'");
  });
});

describe("breaks flattened with narrow no-break spaces", () => {
  it("restores headings and lists", () => {
    const body = "Intro.\nUse *will have*. \u202f##\u202fFormation \u202f- **avoir**: aurai \u202f- **être**: serai";
    const { container } = render(<Markdown>{body}</Markdown>);
    expect(container.textContent).not.toMatch(/#|\*/);
    expect(container.querySelector("h3")?.textContent).toBe("Formation");
    expect(container.querySelectorAll("li")).toHaveLength(2);
  });
});

describe("headings and examples the model wrapped in other markup", () => {
  it("unwraps bold around a heading, indented headings and text fences", () => {
    const body = "**### The passive voice**\nIntro.\n\n    #### Simple sentences\n\n```text\nJe **mange**.\n```";
    const { container } = render(<Markdown>{body}</Markdown>);
    expect(container.textContent).not.toMatch(/#|\*/);
    expect([...container.querySelectorAll("h4, h5")].map((h) => h.textContent)).toEqual([
      "The passive voice",
      "Simple sentences",
    ]);
    expect(container.querySelector("strong")?.textContent).toBe("mange");
  });
});
