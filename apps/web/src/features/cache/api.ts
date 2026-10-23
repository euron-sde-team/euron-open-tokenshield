"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";

export function useCacheStats() {
  return useQuery({
    queryKey: qk.cacheStats,
    queryFn: () => unwrap(api.GET("/api/v1/cache/stats")),
    staleTime: STALE.analytics,
  });
}

export function useCacheEntries(projectId?: string) {
  return useQuery({
    queryKey: qk.cacheEntries(projectId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/cache/entries", { params: { query: { project_id: projectId ?? null, limit: 25 } } })),
    staleTime: STALE.analytics,
  });
}

export function useInvalidateEntry() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (keyHash: string) =>
      unwrap(api.DELETE("/api/v1/cache/entries/{key_hash}", { params: { path: { key_hash: keyHash } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.cacheAll }),
  });
}

export function usePurgeCache() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string | null) => unwrap(api.POST("/api/v1/cache/purge", { body: { project_id: projectId } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.cacheAll }),
  });
}
