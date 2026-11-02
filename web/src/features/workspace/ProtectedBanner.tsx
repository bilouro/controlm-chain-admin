import { useState } from "react";
import { useWorkspace } from "@/lib/api/queries";
import { ReadOnlyNotice } from "./ReadOnlyNotice";
import { WorkspaceDialog } from "./WorkspaceDialog";

/** Below the header on a read-only branch (the trunk): edits need a release. */
export function ProtectedBanner() {
  const workspace = useWorkspace();
  const [isOpen, setIsOpen] = useState(false);
  if (!workspace.data || workspace.data.editable) return null;
  return (
    <>
      <ReadOnlyNotice
        workspace={workspace.data}
        onStart={() => setIsOpen(true)}
        className="border-x-0 border-t-0"
      />
      {isOpen && <WorkspaceDialog onClose={() => setIsOpen(false)} />}
    </>
  );
}
