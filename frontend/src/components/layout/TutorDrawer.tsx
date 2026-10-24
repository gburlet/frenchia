import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
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
        <SheetContent aria-describedby="tutor-description">
          <SheetTitle>Tuteur</SheetTitle>
          <SheetDescription id="tutor-description">
            Your contextual tutor will live here.
          </SheetDescription>
        </SheetContent>
      </Sheet>
    </>
  );
}
