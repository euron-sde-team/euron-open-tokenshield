"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";

export interface RequestFilters {
  project_id?: string;
  model?: string;
  status?: string;
  cache_status?: string;
  q?: string;
  task_id?: string;
}

const PAGE = 50;

/** Strip empty values so the key and the query string only carry real filters. */
export function cleanFilters(f: RequestFilters): RequestFilters {
  const out: RequestFilters = {};
  for (const [k, v] of Object.entries(f) as [keyof RequestFilters, string | undefined][]) {
    const trimmed = v?.trim();
    if (trimmed) out[k] = trimmed;
  }
  return out;
}

/**
 * Keyset-paginated request log. With auto refresh on, the first page refetches every
 * 5 s; older pages stay as loaded.
 */
export function useRequestLog(filters: RequestFilters, autoRefresh: boolean) {
  const clean = cleanFilters(filters);
  return useInfiniteQuery({
    queryKey: qk.events(clean),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/api/v1/usage/events", { params: { query: { ...clean, cursor: pageParam, limit: PAGE } } })),
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: autoRefresh ? STALE.requestsLive : STALE.config,
    refetchInterval: autoRefresh ? 5_000 : false,
    maxPages: 20,
  });
}

export function useRequestDetail(requestId: string | null) {
  return useQuery({
    queryKey: qk.event(requestId ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/v1/usage/events/{request_id}", { params: { path: { request_id: requestId ?? "" } } })),
    enabled: !!requestId,
    // Usage events are append-only; a loaded detail only changes through reconciliation.
    staleTime: STALE.config,
  });
}
