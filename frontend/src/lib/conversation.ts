// The one seam for conversation_id lifecycle — nothing else in the
// app should read/write this localStorage key directly.

const CONVERSATION_ID_KEY = "capitalforge:conversation-id";

export function getOrCreateConversationId(): string {
  const existing = localStorage.getItem(CONVERSATION_ID_KEY);
  if (existing) {
    return existing;
  }
  const fresh = crypto.randomUUID();
  localStorage.setItem(CONVERSATION_ID_KEY, fresh);
  return fresh;
}

/**
 * Starts a brand new conversation, discarding the old conversation_id.
 * The old conversation's data still exists in the backend's
 * ConversationStore under its original id — this only changes which
 * conversation the frontend is pointed at.
 */
export function startNewConversation(): string {
  const fresh = crypto.randomUUID();
  localStorage.setItem(CONVERSATION_ID_KEY, fresh);
  return fresh;
}