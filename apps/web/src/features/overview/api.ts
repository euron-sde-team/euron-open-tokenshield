"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { BreakdownBy, RangeKey } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

const live = { staleTime: STALE.analytics, refetchInterval: 30_000, placeholderData: keepPreviousData } as const;

export function useOverview(range: RangeKey, projectId?: string) {
  return useQuery({
    queryKey: qk.overview(range, projectId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/analytics/overview", { params: { query: { range, project_id: projectId ?? null } } })),
    ...live,
  });
}

export function useTimeseries(range: RangeKey, projectId?: string) {
  return useQuery({
    queryKey: qk.timeseries(range, projectId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/analytics/timeseries", { params: { query: { range, project_id: projectId ?? null } } })),
    ...live,
  });
}

export function useBreakdown(by: BreakdownBy, range: RangeKey, projectId?: string) {
  return useQuery({
    queryKey: qk.breakdown(by, range, projectId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/analytics/breakdown", { params: { query: { by, range, project_id: projectId ?? null } } })),
    ...live,
  });
}

export function useTasks(range: RangeKey, projectId?: string) {
  return useQuery({
    queryKey: qk.tasks(range, projectId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/analytics/tasks", { params: { query: { range, project_id: projectId ?? null } } })),
    ...live,
  });
}
