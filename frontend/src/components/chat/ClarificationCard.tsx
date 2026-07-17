import { useState } from "react";
import { Button } from "@/components/ui/button";

interface ClarificationCardProps {
  message: string;
  onSubmit: (value: string) => void;
  disabled?: boolean;
}

export function ClarificationCard({ message, onSubmit, disabled }: ClarificationCardProps) {
  const [value, setValue] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim() || disabled) return;
    onSubmit(value.trim());
    setValue("");
  }

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-900 dark:bg-amber-950">
      <p className="mb-3">{message}</p>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="number"
          step="0.01"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
          placeholder="Enter a price"
          className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button type="submit" size="sm" disabled={disabled || !value.trim()}>
          Submit
        </Button>
      </form>
    </div>
  );
}