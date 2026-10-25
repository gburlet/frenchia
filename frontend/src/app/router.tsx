import { createBrowserRouter, type RouteObject } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { Dashboard } from "@/routes/Dashboard";
import { NotFound } from "@/routes/NotFound";
import { CurriculumPage } from "@/features/curriculum/CurriculumPage";
import { LessonPage } from "@/features/lessons/LessonPage";
import { TranslatePage } from "@/features/practice/TranslatePage";
import { ProgressPage } from "@/routes/placeholders";
import { VerbsPage } from "@/features/verbs/VerbsPage";
import { VerbDetailPage } from "@/features/verbs/VerbDetailPage";
import { VerbDrillPage } from "@/features/verbs/VerbDrillPage";
import { VocabPage } from "@/features/vocab/VocabPage";
import { VocabSetPage } from "@/features/vocab/VocabSetPage";
import { VocabReviewPage } from "@/features/vocab/VocabReviewPage";

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
          { path: "lessons/:lessonId", element: <LessonPage /> },
          { path: "practice/translate", element: <TranslatePage /> },
          { path: "practice/verbs", element: <VerbsPage /> },
          { path: "practice/verbs/drill", element: <VerbDrillPage /> },
          { path: "practice/verbs/:slug", element: <VerbDetailPage /> },
          { path: "practice/vocab", element: <VocabPage /> },
          { path: "practice/vocab/review", element: <VocabReviewPage /> },
          { path: "practice/vocab/sets/:slug", element: <VocabSetPage /> },
          { path: "progress", element: <ProgressPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFound /> },
];

export const createRouter = () => createBrowserRouter(routes);
