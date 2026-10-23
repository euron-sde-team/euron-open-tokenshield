"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { ApiKeyIn } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useKeys(projectId?: string, includeRevoked = false) {
  return useQuery({
    queryKey: qk.keys(projectId, includeRevoked),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/keys", { params: { query: { project_id: projectId ?? null, include_revoked: includeRevoked } } }),
      ),
    staleTime: STALE.config,
  });
}

export function useCreateKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ApiKeyIn) => unwrap(api.POST("/api/v1/keys", { body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.keysAll });
      void client.invalidateQueries({ queryKey: qk.projectsAll });
      void client.invalidateQueries({ queryKey: qk.system });
    },
  });
}

export function useRevokeKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/keys/{key_id}/revoke", { params: { path: { key_id: id } } })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.keysAll });
      void client.invalidateQueries({ queryKey: qk.projectsAll });
      void client.invalidateQueries({ queryKey: qk.system });
    },
  });
}
