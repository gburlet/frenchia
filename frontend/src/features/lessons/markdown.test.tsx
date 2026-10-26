import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { cleanMarkdown } from "./cleanMarkdown";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("turns HTML breaks and stray symbols into line breaks and drops comments", () => {
    expect(cleanMarkdown("a<br>b<br/>c⟩⟩⟩d⏎e<!-- x -->")).toBe("a\nb\nc\nd\ne");
  });

  it("renders a table whose rows were separated by <br>", () => {
    render(<Markdown>{"| Verbe | Forme |<br>|---|---|<br>| parler | parlé |"}</Markdown>);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByText(/<br>/)).not.toBeInTheDocument();
  });
});
