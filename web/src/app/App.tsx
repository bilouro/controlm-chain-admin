import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router";
import { ChainTablePage } from "@/features/chain-table/ChainTablePage";
import { ChangeProvider } from "@/features/changes/ChangeProvider";
import { CommitButton } from "@/features/commit/CommitButton";
import { ComparePage } from "@/features/compare/ComparePage";
import { FolderPage } from "@/features/folder-graph/FolderPage";
import { JobPage } from "@/features/job-detail/JobPage";
import { ValidatePage } from "@/features/validate/ValidatePage";
import { RepoBadge } from "@/features/repo/RepoBadge";
import { cn } from "@/lib/utils";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "rounded-md px-3 py-1.5 text-sm font-medium transition-colors hover:bg-surface-2",
          isActive ? "bg-accent-soft text-accent" : "text-muted",
        )
      }
    >
      {children}
    </NavLink>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-4 border-b border-border bg-surface px-4 py-2">
        <span className="font-semibold tracking-tight">ctmchain</span>
        <nav aria-label="Main" className="flex gap-1">
          <NavItem to="/">Chains</NavItem>
          <NavItem to="/validate">Validate</NavItem>
          <NavItem to="/compare">Compare</NavItem>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <CommitButton />
          <RepoBadge />
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto">{children}</main>
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<ChainTablePage />} />
      <Route path="/folders" element={<Navigate to="/" replace />} />
      <Route path="/folders/:folder" element={<FolderPage />} />
      <Route path="/folders/:folder/jobs/:job" element={<JobPage />} />
      <Route path="/validate" element={<ValidatePage />} />
      <Route path="/compare" element={<ComparePage />} />
      <Route path="*" element={<p className="p-6 text-muted">Page not found.</p>} />
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ChangeProvider>
          <AppShell>
            <AppRoutes />
          </AppShell>
        </ChangeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
