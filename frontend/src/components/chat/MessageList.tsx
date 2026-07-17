import { toChatMessage } from "@/lib/messages";
import { cn } from "@/lib/utils";

interface MessageListProps {
  messages: Record<string, unknown>[];
}

export function MessageList({ messages }: MessageListProps) {
  const chatMessages = messages
    .map(toChatMessage)
    .filter((m): m is NonNullable<typeof m> => m !== null);

  if (chatMessages.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Describe your trading rules to get started — for example, "Buy Apple
        below $180, sell above $195."
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {chatMessages.map((message, i) => (
        <div
          key={i}
          className={cn(
            "max-w-[80%] rounded-lg px-3 py-2 text-sm",
            message.role === "user"
              ? "ml-auto bg-primary text-primary-foreground"
              : "bg-muted text-foreground"
          )}
        >
          {message.content}
        </div>
      ))}
    </div>
  );
}