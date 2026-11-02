/** A branch name from the subject: `fix: update job X` -> `release/update-job-x`. */
export function branchFor(subject: string, prefix = "release/"): string {
  const text = subject.includes(":") ? subject.slice(subject.indexOf(":") + 1) : subject;
  const slug = text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
    .replace(/-+$/, "");
  return `${prefix}${slug || "changes"}`;
}
