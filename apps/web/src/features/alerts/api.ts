"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { AlertList } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useAlerts(includeAcknowledged = false) {
  return useQuery({
    queryKey: qk.alerts(includeAcknowledged),
    queryFn: () =>
      unwrap(api.GET("/api/v1/alerts", { params: { query: { include_acknowledged: includeAcknowledged, limit: 50 } } })),
    staleTime: STALE.analytics,
    refetchInterval: 30_000,
  });
}

export function useAckAlert() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unwrap(api.POST("/api/v1/alerts/{alert_id}/ack", { params: { path: { alert_id: id } } })),
    onMutate: async (id) => {
      await client.cancelQueries({ queryKey: qk.alertsAll });
      const key = qk.alerts(false);
      const previous = client.getQueryData<AlertList>(key);
      if (previous) {
        client.setQueryData<AlertList>(key, {
          items: previous.items.filter((a) => a.id !== id),
          unacknowledged: Math.max(0, previous.unacknowledged - 1),
        });
      }
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) client.setQueryData(qk.alerts(false), ctx.previous);
    },
    onSettled: () => void client.invalidateQueries({ queryKey: qk.alertsAll }),
  });
}

export function useAckAllAlerts() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/alerts/ack-all")),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.alertsAll }),
  });
}
