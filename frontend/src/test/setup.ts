import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// findBy*/waitFor default to 1 s, which flakes when the local LLM is busy on the same machine.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
  try {
    sessionStorage.clear();
  } catch {
    /* ignore */
  }
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});
