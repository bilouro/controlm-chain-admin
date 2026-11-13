import { useState, type FormEvent } from "react";
import { useRepo } from "@/lib/api/queries";
import { useChanges } from "@/features/changes/changes-context";
import { Button, TextInput } from "@/components/ui";

/** The technical attributes: what Control-M writes by itself, kept in meta and never compared. */
export function TechnicalAttributes() {
  const repo = useRepo();
  const { propose } = useChanges();
  const [name, setName] = useState("");
  const names = repo.data?.volatile_attributes ?? [];

  const handleAdd = (event: FormEvent) => {
    event.preventDefault();
    const added = name.trim().toUpperCase();
    if (!added) return;
    propose({ op: "set-technical", params: { add: [added] } });
    setName("");
  };

  return (
    <section aria-label="Technical attributes" className="space-y-2">
      <h2 className="text-base font-semibold">Technical attributes</h2>
      <p className="text-sm text-muted">
        What Control-M writes by itself (ids, dates, versions): kept in <code>meta/</code>, never
        compared, never an exception. Add a name that turned out to be noise; remove one that
        matters after all. Its values move between the jobs and <code>meta/</code>, the exports do
        not change.
      </p>
      <ul aria-label="Technical attribute names" className="flex flex-wrap gap-2">
        {names.map((technical) => (
          <li
            key={technical}
            className="flex items-center gap-1 rounded-md border border-border px-2 py-1 font-mono text-xs"
          >
            {technical}
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Remove ${technical} from the technical attributes`}
              onClick={() => propose({ op: "set-technical", params: { remove: [technical] } })}
            >
              ×
            </Button>
          </li>
        ))}
      </ul>
      <form
        aria-label="New technical attribute"
        onSubmit={handleAdd}
        className="flex items-end gap-2"
      >
        <label className="text-xs text-muted">
          Attribute
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="LAST_UPLOAD"
            className="block"
          />
        </label>
        <Button type="submit" size="sm" disabled={!name.trim()}>
          Add
        </Button>
      </form>
    </section>
  );
}
