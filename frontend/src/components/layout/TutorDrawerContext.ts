import { createContext, useContext } from "react";

export interface TutorDrawerValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
}

export const TutorDrawerContext = createContext<TutorDrawerValue | null>(null);

export function useTutorDrawer(): TutorDrawerValue {
  const value = useContext(TutorDrawerContext);
  if (!value) throw new Error("useTutorDrawer must be used within TutorDrawerProvider");
  return value;
}
