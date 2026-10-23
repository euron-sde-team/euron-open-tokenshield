"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { ApiError, parseApiError } from "@/lib/api/errors";
import type { PlaygroundRequest } from "@/lib/api/types";
import { qk } from "@/lib/query-keys";

export interface GatewayHeaders {
  requestId: string | null;
  cache: string | null;
  costUsd: number | null;
  estimatedCostUsd: number | null;
  avoidedCostUsd: number | null;
  priced: boolean;
}

export interface ChatCompletion {
  id?: string;
  model?: string;
  choices?: { index: number; message?: { role: string; content: string | null }; finish_reason?: string | null }[];
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number; prompt_tokens_details?: { cached_tokens?: number } };
}

export interface PlaygroundResult {
  body: ChatCompletion;
  headers: GatewayHeaders;
  status: number;
  elapsedMs: number;
}

function num(v: string | null): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Read the x-tokenshield-* response headers the gateway adds to every answer. */
export function readGatewayHeaders(h: Headers): GatewayHeaders {
  return {
    requestId: h.get("x-tokenshield-request-id"),
    cache: h.get("x-tokenshield-cache"),
    costUsd: num(h.get("x-tokenshield-cost-usd")),
    estimatedCostUsd: num(h.get("x-tokenshield-estimated-cost-usd")),
    avoidedCostUsd: num(h.get("x-tokenshield-avoided-cost-usd")),
    priced: h.get("x-tokenshield-priced") !== "false",
  };
}

/** Error from the playground, keeping the gateway headers when the API sent any. */
export class PlaygroundError extends ApiError {
  readonly headers: GatewayHeaders;
  constructor(base: ApiError, headers: GatewayHeaders) {
    super({ status: base.status, code: base.code, type: base.type, message: base.message, details: base.details });
    this.headers = headers;
  }
}

export function usePlaygroundRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: PlaygroundRequest): Promise<PlaygroundResult> => {
      const started = performance.now();
      const res = await api.POST("/api/v1/playground/chat", { body }).catch(() => {
        throw parseApiError(0, null);
      });
      const headers = readGatewayHeaders(res.response.headers);
      if (!res.response.ok) throw new PlaygroundError(parseApiError(res.response.status, res.error), headers);
      return { body: res.data as ChatCompletion, headers, status: res.response.status, elapsedMs: Math.round(performance.now() - started) };
    },
    onSettled: () => {
      // A playground call is a real gateway request: refresh what it touched.
      void client.invalidateQueries({ queryKey: qk.usageAll });
      void client.invalidateQueries({ queryKey: qk.analyticsAll });
      void client.invalidateQueries({ queryKey: qk.budgets });
      void client.invalidateQueries({ queryKey: qk.cacheAll });
    },
  });
}
