import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { TutorDrawer } from "./TutorDrawer";
import { TutorDrawerProvider } from "./TutorDrawerProvider";

function setup() {
  render(
    <TutorDrawerProvider>
      <input aria-label="field" />
      <TutorDrawer />
    </TutorDrawerProvider>,
  );
  return userEvent.setup();
}

describe("TutorDrawer", () => {
  it("opens from the tab and closes with Escape", async () => {
    const user = setup();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tuteur" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Tuteur");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("toggles with the t key", async () => {
    const user = setup();
    await user.keyboard("t");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("ignores t while typing in an input", async () => {
    const user = setup();
    await user.click(screen.getByLabelText("field"));
    await user.keyboard("t");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
