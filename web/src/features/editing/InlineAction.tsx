import { useState } from "react";
import { Button, TextInput } from "@/components/ui";

/** Inline "Rename" / "Move" actions of the header. */
export function InlineAction({
  label,
  placeholder,
  onSubmit,
}: {
  label: string;
  placeholder: string;
  onSubmit: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  if (!open) {
    return (
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        {label}
      </Button>
    );
  }
  return (
    <span className="inline-flex items-center gap-1">
      <TextInput
        aria-label={label}
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="w-64"
      />
      <Button
        size="sm"
        disabled={!value}
        aria-label={`Review ${label.toLowerCase()}`}
        onClick={() => {
          onSubmit(value);
          setOpen(false);
          setValue("");
        }}
      >
        Review
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
        Cancel
      </Button>
    </span>
  );
}
