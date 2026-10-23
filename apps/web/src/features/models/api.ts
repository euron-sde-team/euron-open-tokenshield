"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { ModelIn, ModelUpdate, PriceIn, ProviderIn, ProviderUpdate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useModels() {
  return useQuery({ queryKey: qk.models, queryFn: () => unwrap(api.GET("/api/v1/models")), staleTime: STALE.config });
}

export function usePrices(modelId: string | null) {
  return useQuery({
    queryKey: qk.prices(modelId ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/models/{model_id}/prices", { params: { path: { model_id: modelId ?? "" } } })),
    enabled: !!modelId,
    staleTime: STALE.config,
  });
}

export function useCreateModel() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ModelIn) => unwrap(api.POST("/api/v1/models", { body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.models });
      void client.invalidateQueries({ queryKey: qk.providers });
    },
  });
}

export function useUpdateModel() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ModelUpdate }) =>
      unwrap(api.PATCH("/api/v1/models/{model_id}", { params: { path: { model_id: id } }, body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.models }),
  });
}

export function usePublishPrice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ modelId, body }: { modelId: string; body: PriceIn }) =>
      unwrap(api.POST("/api/v1/models/{model_id}/prices", { params: { path: { model_id: modelId } }, body })),
    onSuccess: (_p, { modelId }) => {
      void client.invalidateQueries({ queryKey: qk.models });
      void client.invalidateQueries({ queryKey: qk.prices(modelId) });
    },
  });
}

export function useProviders() {
  return useQuery({ queryKey: qk.providers, queryFn: () => unwrap(api.GET("/api/v1/providers")), staleTime: STALE.config });
}

export function useCreateProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ProviderIn) => unwrap(api.POST("/api/v1/providers", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.providers }),
  });
}

export function useUpdateProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ProviderUpdate }) =>
      unwrap(api.PATCH("/api/v1/providers/{provider_id}", { params: { path: { provider_id: id } }, body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.providers });
      void client.invalidateQueries({ queryKey: qk.models });
    },
  });
}

export function useTestProvider() {
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/api/v1/providers/{provider_id}/test", { params: { path: { provider_id: id } } })),
  });
}
