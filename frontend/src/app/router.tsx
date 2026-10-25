import { createBrowserRouter, type RouteObject } from "react-router";
import { FullPageLoader } from "@/components/FullPageLoader";
import { AppShell } from "@/components/layout/AppShell";
import { RouteError } from "@/components/RouteError";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { Dashboard } from "@/routes/Dashboard";
import { NotFound } from "@/routes/NotFound";

export const routes: RouteObject[] = [
  {
    hydrateFallbackElement: <FullPageLoader />,
    errorElement: <RouteError fullPage />,
    children: [
      { path: "/login", element: <LoginPage /> },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AppShell />,
            children: [
              {
                // Pages other than the dashboard load on first visit (smaller first download).
                errorElement: <RouteError />,
                children: [
                  { index: true, element: <Dashboard /> },
                  { path: "curriculum", lazy: () => import("@/features/curriculum/CurriculumPage").then((m) => ({ Component: m.CurriculumPage })) },
                  { path: "lessons/:lessonId", lazy: () => import("@/features/lessons/LessonPage").then((m) => ({ Component: m.LessonPage })) },
                  { path: "practice/translate", lazy: () => import("@/features/practice/TranslatePage").then((m) => ({ Component: m.TranslatePage })) },
                  { path: "practice/verbs", lazy: () => import("@/features/verbs/VerbsPage").then((m) => ({ Component: m.VerbsPage })) },
                  { path: "practice/verbs/drill", lazy: () => import("@/features/verbs/VerbDrillPage").then((m) => ({ Component: m.VerbDrillPage })) },
                  { path: "practice/verbs/:slug", lazy: () => import("@/features/verbs/VerbDetailPage").then((m) => ({ Component: m.VerbDetailPage })) },
                  { path: "practice/vocab", lazy: () => import("@/features/vocab/VocabPage").then((m) => ({ Component: m.VocabPage })) },
                  { path: "practice/vocab/review", lazy: () => import("@/features/vocab/VocabReviewPage").then((m) => ({ Component: m.VocabReviewPage })) },
                  { path: "practice/vocab/sets/:slug", lazy: () => import("@/features/vocab/VocabSetPage").then((m) => ({ Component: m.VocabSetPage })) },
                  { path: "practice/review", lazy: () => import("@/features/progress/ReviewPage").then((m) => ({ Component: m.ReviewPage })) },
                  { path: "progress", lazy: () => import("@/features/progress/ProgressPage").then((m) => ({ Component: m.ProgressPage })) },
                ],
              },
            ],
          },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
];

export const createRouter = () => createBrowserRouter(routes);
