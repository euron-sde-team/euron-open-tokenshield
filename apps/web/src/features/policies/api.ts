"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Rule, RuleIn, RuleUpdate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function usePolicies() {
  return useQuery({ queryKey: qk.policies, queryFn: () => unwrap(api.GET("/api/v1/policies")), staleTime: STALE.config });
}

export function useCreatePolicy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: RuleIn) => unwrap(api.POST("/api/v1/policies", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.policies }),
  });
}

/** The enabled switch flips instantly; a failure puts it back. */
export function useUpdatePolicy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: RuleUpdate }) =>
      unwrap(api.PATCH("/api/v1/policies/{rule_id}", { params: { path: { rule_id: id } }, body })),
    onMutate: async ({ id, body }) => {
      if (body.enabled == null) return {};
      await client.cancelQueries({ queryKey: qk.policies });
      const previous = client.getQueryData<Rule[]>(qk.policies);
      client.setQueryData<Rule[]>(qk.policies, (list) =>
        list?.map((r) => (r.id === id ? { ...r, enabled: body.enabled ?? r.enabled } : r)),
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) client.setQueryData(qk.policies, ctx.previous);
    },
    onSettled: () => void client.invalidateQueries({ queryKey: qk.policies }),
  });
}

export function useDeletePolicy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/policies/{rule_id}", { params: { path: { rule_id: id } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.policies }),
  });
}
