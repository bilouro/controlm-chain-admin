import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { render, type RenderOptions } from "@testing-library/react";
import { ChangeProvider } from "@/features/changes/ChangeProvider";

/** Render inside a fresh QueryClient and a MemoryRouter positioned at `path` with `routes`. */
export function renderAt(
  ui: ReactElement,
  {
    path = "/",
    pattern = "*",
    ...options
  }: RenderOptions & { path?: string; pattern?: string } = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <ChangeProvider>
          <Routes>
            <Route path={pattern} element={ui} />
            <Route path="*" element={<p>other page</p>} />
          </Routes>
        </ChangeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
    options,
  );
}
