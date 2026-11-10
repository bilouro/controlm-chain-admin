import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router";
import { AssistantPanel } from "@/features/assistant/AssistantPanel";
import { ChainTablePage } from "@/features/chain-table/ChainTablePage";
import { ChangeProvider } from "@/features/changes/ChangeProvider";
import { CommitButton } from "@/features/commit/CommitButton";
import { ComparePage } from "@/features/compare/ComparePage";
import { FolderPage } from "@/features/folder-graph/FolderPage";
import { ImportPage } from "@/features/intake/ImportPage";
import { EnvBadge } from "@/features/environments/EnvBadge";
import { EnvProvider } from "@/features/environments/EnvProvider";
import { EnvSelect } from "@/features/environments/EnvSelect";
import { EnvironmentsPage } from "@/features/environments/EnvironmentsPage";
import { MapPage } from "@/features/envmap/MapPage";
import { JobPage } from "@/features/job-detail/JobPage";
import { RefreshPage } from "@/features/refresh/RefreshPage";
import { ValidatePage } from "@/features/validate/ValidatePage";
import { RepoBadge } from "@/features/repo/RepoBadge";
import { BranchButton } from "@/features/workspace/BranchButton";
import { ProtectedBanner } from "@/features/workspace/ProtectedBanner";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

const ASSISTANT_OPEN = "ctmchain-assistant-open";

function openAtStart(): boolean {
  try {
    return sessionStorage.getItem(ASSISTANT_OPEN) === "1";
  } catch {
    return false;
  }
}

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
  const [assistant, setAssistant] = useState(openAtStart);
  const toggleAssistant = (open: boolean) => {
    setAssistant(open);
    try {
      sessionStorage.setItem(ASSISTANT_OPEN, open ? "1" : "0");
    } catch {
      // storage unavailable: the panel closes on reload
    }
  };
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-4 border-b border-border bg-surface px-4 py-2">
        <span className="font-semibold tracking-tight">ctmchain</span>
        <nav aria-label="Main" className="flex gap-1">
          <NavItem to="/">Chains</NavItem>
          <NavItem to="/validate">Validate</NavItem>
          <NavItem to="/compare">Compare</NavItem>
          <NavItem to="/refresh">Refresh</NavItem>
          <NavItem to="/map">Map</NavItem>
          <NavItem to="/import">Import</NavItem>
          <NavItem to="/environments">Environments</NavItem>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <EnvSelect />
          <EnvBadge />
          <BranchButton />
          <CommitButton />
          <RepoBadge />
          <Button
            variant={assistant ? "primary" : "ghost"}
            size="sm"
            aria-expanded={assistant}
            aria-controls="assistant-panel"
            onClick={() => toggleAssistant(!assistant)}
          >
            Assistant
          </Button>
        </div>
      </header>
      <ProtectedBanner />
      <div className="flex min-h-0 flex-1">
        <main className="min-h-0 flex-1 overflow-auto">{children}</main>
        {assistant && (
          <div id="assistant-panel" className="min-h-0">
            <AssistantPanel onClose={() => toggleAssistant(false)} />
          </div>
        )}
      </div>
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
      <Route path="/refresh" element={<RefreshPage />} />
      <Route path="/map" element={<MapPage />} />
      <Route path="/import" element={<ImportPage />} />
      <Route path="/environments" element={<EnvironmentsPage />} />
      <Route path="*" element={<p className="p-6 text-muted">Page not found.</p>} />
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <EnvProvider>
          <ChangeProvider>
            <AppShell>
              <AppRoutes />
            </AppShell>
          </ChangeProvider>
        </EnvProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
