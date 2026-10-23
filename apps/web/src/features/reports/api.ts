"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { ExportIn, ExportJob } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

function hasPending(list: ExportJob[] | undefined): boolean {
  return !!list?.some((e) => e.status !== "ready" && e.status !== "failed" && e.status !== "done");
}

export function useExports() {
  return useQuery({
    queryKey: qk.exports,
    queryFn: () => unwrap(api.GET("/api/v1/exports")),
    staleTime: STALE.config,
    // Poll only while an export is still being written.
    refetchInterval: (q) => (hasPending(q.state.data) ? 2_000 : false),
  });
}

export function useCreateExport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ExportIn) => unwrap(api.POST("/api/v1/exports", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.exports }),
  });
}

export function useDownloadExport() {
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.GET("/api/v1/exports/{export_id}/download", { params: { path: { export_id: id } } })),
  });
}
