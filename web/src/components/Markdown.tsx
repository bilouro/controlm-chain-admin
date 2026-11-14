import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * The little Markdown an assistant answers with: tables, lists, headings, blocks of code, and
 * inside a line what is bold, emphasised or code. Everything else is shown as it was written,
 * line breaks included. It builds elements, never HTML from the text.
 */

// `code`, **bold**, _emphasis_ or *emphasis*; a name such as P77_A_OK or "2 * 3" is neither
const INLINE =
  /`([^`]+)`|\*\*(?=\S)(.+?)(?<=\S)\*\*|(?<![A-Za-z0-9_])_(?=\S)(.+?)(?<=\S)_(?![A-Za-z0-9_])|(?<![*\w])\*(?=[^\s*])([^*]+?)(?<=\S)\*(?![*\w])/g;
const FENCE = /^\s*```/;
const HEADING = /^\s*(#{1,6})\s+(.+?)\s*#*\s*$/;
const ITEM = /^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$/;
const DIVIDER = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const [whole, code, bold, underscored, starred] = match;
    if (match.index > last) out.push(text.slice(last, match.index));
    const key = match.index;
    if (code !== undefined) {
      out.push(
        <code key={key} className="rounded bg-bg px-1 font-mono text-[0.85em]">
          {code}
        </code>,
      );
    } else if (bold !== undefined) {
      out.push(<strong key={key}>{inline(bold)}</strong>);
    } else {
      out.push(<em key={key}>{inline(underscored ?? starred ?? "")}</em>);
    }
    last = match.index + whole.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** The cells of a table line; a bar inside `code` belongs to the cell. */
function cells(line: string): string[] {
  const found: string[] = [];
  let cell = "";
  let isCode = false;
  for (const char of line.trim().replace(/^\|/, "").replace(/\|$/, "")) {
    if (char === "`") isCode = !isCode;
    if (char === "|" && !isCode) {
      found.push(cell.trim());
      cell = "";
    } else cell += char;
  }
  return [...found, cell.trim()];
}

function isTable(lines: string[], at: number): boolean {
  const head = lines[at] ?? "";
  const divider = lines[at + 1] ?? "";
  return head.trim().startsWith("|") && divider.includes("-") && DIVIDER.test(divider);
}

function startsBlock(lines: string[], at: number): boolean {
  const line = lines[at] ?? "";
  return FENCE.test(line) || HEADING.test(line) || ITEM.test(line) || isTable(lines, at);
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr>
            {head.map((title, i) => (
              <th key={i} scope="col" className="border border-border bg-bg px-2 py-1 font-medium">
                {inline(title)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {head.map((_, i) => (
                <td key={i} className="border border-border px-2 py-1 align-top">
                  {inline(row[i] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function blocks(text: string): ReactNode[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let at = 0;
  while (at < lines.length) {
    const line = lines[at] ?? "";
    const key = at;
    if (!line.trim()) {
      at += 1;
    } else if (FENCE.test(line)) {
      const end = lines.findIndex((l, i) => i > at && FENCE.test(l));
      const stop = end === -1 ? lines.length : end;
      out.push(
        <pre key={key} className="overflow-auto rounded-md bg-bg p-2 font-mono text-xs">
          <code>{lines.slice(at + 1, stop).join("\n")}</code>
        </pre>,
      );
      at = stop + 1;
    } else if (isTable(lines, at)) {
      let end = at + 2;
      while (end < lines.length && (lines[end] ?? "").trim().startsWith("|")) end += 1;
      out.push(<Table key={key} head={cells(line)} rows={lines.slice(at + 2, end).map(cells)} />);
      at = end;
    } else if (HEADING.test(line)) {
      const [, marks = "", title = ""] = HEADING.exec(line) ?? [];
      const Tag = marks.length <= 2 ? "h3" : "h4";
      out.push(
        <Tag key={key} className="text-sm font-semibold">
          {inline(title)}
        </Tag>,
      );
      at += 1;
    } else if (ITEM.test(line)) {
      const isNumbered = ITEM.exec(line)?.[2] !== undefined;
      const items: string[] = [];
      while (at < lines.length) {
        const item = ITEM.exec(lines[at] ?? "");
        if (!item || (item[2] !== undefined) !== isNumbered) break;
        items.push(item[3] ?? "");
        at += 1;
      }
      const List = isNumbered ? "ol" : "ul";
      out.push(
        <List
          key={key}
          className={cn("space-y-0.5 pl-5", isNumbered ? "list-decimal" : "list-disc")}
        >
          {items.map((item, i) => (
            <li key={i}>{inline(item)}</li>
          ))}
        </List>,
      );
    } else {
      let end = at + 1;
      while (end < lines.length && (lines[end] ?? "").trim() && !startsBlock(lines, end)) end += 1;
      out.push(
        <p key={key} className="whitespace-pre-wrap">
          {inline(lines.slice(at, end).join("\n"))}
        </p>,
      );
      at = end;
    }
  }
  return out;
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  return <div className={cn("space-y-2 text-sm", className)}>{blocks(text)}</div>;
}
