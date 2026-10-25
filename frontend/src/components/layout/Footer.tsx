import { ShortcutsDialog } from "./ShortcutsDialog";

export function Footer() {
  return (
    <footer className="border-t border-card-border bg-chrome">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-sm text-muted">
        <span>Frenchia · Apprendre le français québécois, en local.</span>
        <ShortcutsDialog />
      </div>
    </footer>
  );
}
