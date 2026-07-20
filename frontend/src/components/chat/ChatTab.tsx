import { useConversation } from "@/hooks/useConversation";
import { useActiveAgent } from "@/hooks/useActiveAgent";
import { useCurrentVersion } from "@/hooks/useCurrentVersion";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import { AppliedOperationsDiff } from "./AppliedOperationsDiff";
import { ClarificationCard } from "./ClarificationCard";
import { DisambiguationCard } from "./DisambiguationCard";
import { DraftPane } from "./DraftPane";
import { Button } from "@/components/ui/button";
import { useLocation } from "react-router-dom";

export function ChatTab() {
  const {
    session,
    isSessionLoading,
    sendMessage,
    isSending,
    lastTranslateResult,
    confirmDraft,
    isConfirming,
    lastConfirmResult,
    resetConversation,
  } = useConversation();

  const location = useLocation();
  const prefillMessage = (location.state as { prefillMessage?: string } | null)?.prefillMessage;

  const { activeAgent } = useActiveAgent();
  const { data: currentVersion } = useCurrentVersion(
    !session?.draft && activeAgent ? activeAgent.id : null
  );

  // Draft in progress takes priority (actively being edited); otherwise
  // fall back to the real confirmed rules, so the panel is never empty
  // once an agent has been confirmed, regardless of conversation state.
  const draft = lastTranslateResult?.draft ?? session?.draft ?? currentVersion?.config_json ?? null;
  const status = lastTranslateResult?.status;

  function handleDisambiguationSelect(symbol: string) {
    void sendMessage(symbol);
  }

  function handleClarificationSubmit(value: string) {
    void sendMessage(value);
  }

  async function handleConfirm() {
    const result = await confirmDraft(undefined);
    if (result.confirmed) {
      resetConversation();
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="flex h-[600px] flex-col gap-3 rounded-lg border border-border p-4">
        <div className="flex-1 overflow-y-auto">
          {isSessionLoading ? (
            <p className="text-sm text-muted-foreground">Loading conversation...</p>
          ) : (
            <MessageList messages={session?.messages ?? []} />
          )}
        </div>

        {status === "needs_clarification" && lastTranslateResult?.clarification_message && (
          <ClarificationCard
            message={lastTranslateResult.clarification_message}
            onSubmit={handleClarificationSubmit}
            disabled={isSending}
          />
        )}

        {status === "needs_disambiguation" && lastTranslateResult?.disambiguation_message && (
          <DisambiguationCard
            message={lastTranslateResult.disambiguation_message}
            candidates={lastTranslateResult.disambiguation_candidates}
            onSelect={handleDisambiguationSelect}
            disabled={isSending}
          />
        )}

        {status === "updated_draft" && lastTranslateResult && (
          <AppliedOperationsDiff operations={lastTranslateResult.applied_operations} />
        )}

        {status === "error" && lastTranslateResult?.error_message && (
          <p className="text-sm text-destructive">{lastTranslateResult.error_message}</p>
        )}

        <MessageInput
          onSend={(msg) => void sendMessage(msg)}
          disabled={isSending}
          initialValue={prefillMessage}
        />

        {lastConfirmResult && !lastConfirmResult.confirmed && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive">
            {lastConfirmResult.issues.map((issue, i) => (
              <div key={i}>{issue.message}</div>
            ))}
          </div>
        )}

        <Button
          onClick={() => void handleConfirm()}
          disabled={!draft || draft.asset_rules.length === 0 || isConfirming}
        >
          {isConfirming ? "Confirming..." : "Confirm Strategy"}
        </Button>
      </div>

      <DraftPane draft={draft} />
    </div>
  );
}