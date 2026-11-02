import { useState, type FormEvent } from "react";
import { setToken } from "@/lib/api/session";
import { Button, TextInput } from "@/components/ui";

/** The token from the URL printed by `ctmchain serve`, or the token itself. */
function tokenFrom(text: string): string {
  const value = text.trim();
  try {
    return new URL(value).searchParams.get("token") ?? value;
  } catch {
    return value;
  }
}

export function TokenForm({ onToken }: { onToken: () => void }) {
  const [value, setValue] = useState("");
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!value.trim()) return;
    setToken(tokenFrom(value));
    onToken();
  };
  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2 text-sm">
      <label className="flex-1 text-xs text-muted">
        Editing URL or token
        <TextInput
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="http://127.0.0.1:8765/?token=…"
          className="block w-full"
        />
      </label>
      <Button type="submit">Use this token</Button>
    </form>
  );
}
