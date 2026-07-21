// TanStack Query wiring for the AI Agent chat: session restore,
// translate mutation, confirm mutation. Components consume this hook,
// never call api/agent.ts functions directly.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { confirm, getConversationSession, translate } from "@/api/agent";
import { getOrCreateConversationId, startNewConversation } from "@/lib/conversation";
import { useCurrentUser } from "@/lib/constants";
import type { ConfirmRequest } from "@/types/agent";

export function useConversation() {
  const [conversationId, setConversationId] = useState(() => getOrCreateConversationId());
  const queryClient = useQueryClient();
  const { userId } = useCurrentUser();

  const sessionQuery = useQuery({
    queryKey: ["agent", "conversations", conversationId],
    queryFn: () => getConversationSession(conversationId),
  });

  const translateMutation = useMutation({
    mutationFn: (message: string) => translate({ conversation_id: conversationId, user_id: userId, message }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["agent", "conversations", conversationId],
      });
    },
  });

  const confirmMutation = useMutation({
    mutationFn: (strategyId?: string) =>
      confirm({
        user_id: userId,
        conversation_id: conversationId,
        strategy_id: strategyId ?? null,
      } satisfies ConfirmRequest),
    onSuccess: (result) => {
      if (result.confirmed) {
        queryClient.invalidateQueries({ queryKey: ["strategies"] });
      }
    },
  });

  function resetConversation() {
    const fresh = startNewConversation();
    setConversationId(fresh);
    queryClient.invalidateQueries({ queryKey: ["agent", "conversations"] });
  }

  return {
    conversationId,
    session: sessionQuery.data,
    isSessionLoading: sessionQuery.isLoading,
    sendMessage: translateMutation.mutateAsync,
    isSending: translateMutation.isPending,
    lastTranslateResult: translateMutation.data,
    confirmDraft: confirmMutation.mutateAsync,
    isConfirming: confirmMutation.isPending,
    lastConfirmResult: confirmMutation.data,
    resetConversation,
  };
}