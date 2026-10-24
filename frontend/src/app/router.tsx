import { createBrowserRouter, type RouteObject } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { Dashboard } from "@/routes/Dashboard";
import { NotFound } from "@/routes/NotFound";
import {
  CurriculumPage,
  ProgressPage,
  TranslatePage,
  VerbsPage,
  VocabPage,
} from "@/routes/placeholders";

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Dashboard /> },
          { path: "curriculum", element: <CurriculumPage /> },
          { path: "practice/translate", element: <TranslatePage /> },
          { path: "practice/verbs", element: <VerbsPage /> },
          { path: "practice/vocab", element: <VocabPage /> },
          { path: "progress", element: <ProgressPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFound /> },
];

export const createRouter = () => createBrowserRouter(routes);
