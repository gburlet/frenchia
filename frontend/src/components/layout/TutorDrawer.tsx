import { Sheet, SheetContent, SheetDescription } from "@/components/ui/sheet";
import { TutorPanel } from "@/features/tutor/TutorPanel";
import { useTutorDrawer } from "./TutorDrawerContext";

export function TutorDrawer() {
  const { open, setOpen, toggle } = useTutorDrawer();
  return (
    <>
      <button
        type="button"
        onClick={toggle}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-keyshortcuts="t"
        className="fixed right-0 top-1/2 z-30 -translate-y-1/2 cursor-pointer rounded-l-full bg-purple py-4 pl-2.5 pr-2 font-heading text-xs font-bold text-heading shadow-[-4px_0_12px_rgba(0,0,0,0.35)] transition-[filter] duration-200 ease-in-out hover:brightness-[0.85]"
      >
        {/* Vertical text lives on the span: on the button, writing-mode would remap
            Tailwind's logical padding-block (py-*) onto the horizontal axis. */}
        <span className="block [writing-mode:vertical-rl]">Tuteur</span>
      </button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          aria-describedby="tutor-description"
          className="max-w-none gap-0 p-0 sm:w-[420px]"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            document.querySelector<HTMLTextAreaElement>("[data-tutor-input]")?.focus();
          }}
        >
          <SheetDescription id="tutor-description" className="sr-only">
            Ask the local AI tutor about what is on your screen.
          </SheetDescription>
          <TutorPanel />
        </SheetContent>
      </Sheet>
    </>
  );
}
