// Typed functions for agent translate/confirm

import { apiRequest } from "./client";
import type {
  ConfirmRequest,
  ConfirmResponse,
  TranslateRequest,
  TranslateResponse,
} from "@/types/agent";

export function translate(
  payload: TranslateRequest
): Promise<TranslateResponse> {
  return apiRequest<TranslateResponse>("/agent/translate", {
    method: "POST",
    body: payload,
  });
}

export function confirm(payload: ConfirmRequest): Promise<ConfirmResponse> {
  return apiRequest<ConfirmResponse>("/agent/confirm", {
    method: "POST",
    body: payload,
  });
}