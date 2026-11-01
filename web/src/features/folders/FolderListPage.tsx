import { useState } from "react";
import { Link } from "react-router";
import { useFolders } from "@/lib/api/queries";
import { Card, CardHeader, Empty, ErrorBox, Loading, Table, Td, Th } from "@/components/ui";

export function FolderListPage() {
  const [search, setSearch] = useState("");
  const { data, isPending, isError, error } = useFolders(search);

  return (
    <div className="mx-auto max-w-5xl p-4">
      <Card>
        <CardHeader
          title="Folders"
          aside={
            <input
              type="search"
              aria-label="Search folders"
              placeholder="Search folders…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-64 rounded-md border border-border bg-bg px-2.5 py-1 text-sm"
            />
          }
        />
        {isPending && <Loading what="folders" />}
        {isError && <ErrorBox error={error} />}
        {data && data.items.length === 0 && <Empty>No folder matches “{search}”.</Empty>}
        {data && data.items.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th>Folder</Th>
                <Th>Sub-application</Th>
                <Th className="text-right">Jobs</Th>
                <Th className="text-right">Links</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((folder) => (
                <tr key={folder.name} className="hover:bg-surface-2">
                  <Td>
                    <Link
                      to={`/folders/${encodeURIComponent(folder.name)}`}
                      className="font-mono text-accent hover:underline"
                    >
                      {folder.name}
                    </Link>
                    {folder.description && (
                      <div className="text-xs text-muted">{folder.description}</div>
                    )}
                  </Td>
                  <Td className="font-mono text-xs">{folder.sub_application ?? "—"}</Td>
                  <Td className="text-right tabular-nums">{folder.jobs}</Td>
                  <Td className="text-right tabular-nums">{folder.links}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && (
          <p className="px-4 py-2 text-xs text-muted">
            {data.items.length} of {data.total} folders
          </p>
        )}
      </Card>
    </div>
  );
}
