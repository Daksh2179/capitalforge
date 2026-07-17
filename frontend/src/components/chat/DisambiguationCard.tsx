import { Button } from "@/components/ui/button";

interface DisambiguationCardProps {
  message: string;
  candidates: string[];
  onSelect: (symbol: string) => void;
  disabled?: boolean;
}

export function DisambiguationCard({
  message,
  candidates,
  onSelect,
  disabled,
}: DisambiguationCardProps) {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-900 dark:bg-amber-950">
      <p className="mb-3">{message}</p>
      <div className="flex flex-wrap gap-2">
        {candidates.map((symbol) => (
          <Button
            key={symbol}
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() => onSelect(symbol)}
          >
            {symbol}
          </Button>
        ))}
      </div>
    </div>
  );
}