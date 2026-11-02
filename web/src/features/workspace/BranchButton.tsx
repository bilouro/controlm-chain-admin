import { useState } from "react";
import { useWorkspace } from "@/lib/api/queries";
import { Badge, Button } from "@/components/ui";
import { WorkspaceDialog } from "./WorkspaceDialog";

/** The checked-out branch in the header; opens the releases dialog. */
export function BranchButton() {
  const workspace = useWorkspace();
  const [isOpen, setIsOpen] = useState(false);
  if (!workspace.data) return null;
  const { branch, editable } = workspace.data;
  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        title="Releases: where your edits go"
        className="flex items-center gap-1.5"
        onClick={() => setIsOpen(true)}
      >
        <span aria-hidden="true">⎇</span>
        <span className="font-mono">{branch ?? "detached HEAD"}</span>
        {!editable && <Badge tone="warning">read-only</Badge>}
      </Button>
      {isOpen && <WorkspaceDialog onClose={() => setIsOpen(false)} />}
    </>
  );
}
