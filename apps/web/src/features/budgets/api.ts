"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Budget, BudgetIn, BudgetUpdate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useBudgets() {
  return useQuery({
    queryKey: qk.budgets,
    queryFn: () => unwrap(api.GET("/api/v1/budgets")),
    // Spend moves with traffic, so budgets refresh like analytics, not like config.
    staleTime: STALE.analytics,
    refetchInterval: 30_000,
  });
}

export function useCreateBudget() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: BudgetIn) => unwrap(api.POST("/api/v1/budgets", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.budgets }),
  });
}

export function useUpdateBudget() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: BudgetUpdate }) =>
      unwrap(api.PATCH("/api/v1/budgets/{budget_id}", { params: { path: { budget_id: id } }, body })),
    onMutate: async ({ id, body }) => {
      if (body.enabled == null) return {};
      await client.cancelQueries({ queryKey: qk.budgets });
      const previous = client.getQueryData<Budget[]>(qk.budgets);
      client.setQueryData<Budget[]>(qk.budgets, (list) =>
        list?.map((b) => (b.id === id ? { ...b, enabled: body.enabled ?? b.enabled } : b)),
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) client.setQueryData(qk.budgets, ctx.previous);
    },
    onSettled: () => void client.invalidateQueries({ queryKey: qk.budgets }),
  });
}

export function useDeleteBudget() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/budgets/{budget_id}", { params: { path: { budget_id: id } } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.budgets }),
  });
}
