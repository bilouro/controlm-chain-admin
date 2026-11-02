import { useState } from "react";
import { useGit } from "@/lib/api/queries";
import { Button } from "@/components/ui";
import { CommitDialog } from "./CommitDialog";

/** "Commit (n)" in the header: the uncommitted chain files, committed through a dialog. */
export function CommitButton() {
  const git = useGit();
  const [isOpen, setIsOpen] = useState(false);
  if (!git.data) return null;
  const changes = git.data.changes ?? 0;
  return (
    <>
      <Button
        size="sm"
        variant={changes > 0 ? "primary" : "ghost"}
        disabled={changes === 0}
        title={changes === 0 ? "Nothing to commit" : "Commit the edited chain files"}
        onClick={() => setIsOpen(true)}
      >
        {changes > 0 ? `Commit (${changes})` : "Commit"}
      </Button>
      {isOpen && <CommitDialog onClose={() => setIsOpen(false)} />}
    </>
  );
}
