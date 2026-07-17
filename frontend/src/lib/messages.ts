// Safe accessors for the untyped message shape ConversationStore
// returns (backend stores plain {"role", "content"} dicts, typed as
// Record<string, unknown> on this side since that's what it truly is).

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export function toChatMessage(raw: Record<string, unknown>): ChatMessage | null {
  const role = raw.role;
  const content = raw.content;
  if (
    (role === "user" || role === "assistant" || role === "system") &&
    typeof content === "string"
  ) {
    return { role, content };
  }
  return null;
}