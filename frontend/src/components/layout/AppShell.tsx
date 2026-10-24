import { Outlet } from "react-router";
import { Footer } from "./Footer";
import { Header } from "./Header";
import { TutorDrawer } from "./TutorDrawer";
import { TutorDrawerProvider } from "./TutorDrawerProvider";

export function AppShell() {
  return (
    <TutorDrawerProvider>
      <div className="flex min-h-screen flex-col bg-page">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-control focus:bg-purple focus:px-3 focus:py-2 focus:text-heading"
        >
          Skip to content
        </a>
        <Header />
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
          <Outlet />
        </main>
        <Footer />
        <TutorDrawer />
      </div>
    </TutorDrawerProvider>
  );
}
