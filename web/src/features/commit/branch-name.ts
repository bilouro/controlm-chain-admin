/** A branch name from the subject: `fix: update job X` -> `fix/update-job-x`. */
export function branchFor(subject: string): string {
  const [kind, text] = subject.includes(":") ? subject.split(/:\s*/, 2) : ["chore", subject];
  const slug = (text ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
    .replace(/-+$/, "");
  return `${(kind ?? "chore").toLowerCase()}/${slug || "changes"}`;
}
