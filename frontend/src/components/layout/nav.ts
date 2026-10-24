export const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/curriculum", label: "Curriculum", end: false },
  { to: "/practice/translate", label: "Translate", end: false },
  { to: "/practice/verbs", label: "Verbs", end: false },
  { to: "/practice/vocab", label: "Vocabulary", end: false },
  { to: "/progress", label: "Progress", end: false },
] as const;
