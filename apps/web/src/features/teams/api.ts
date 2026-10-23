"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { TeamIn, TeamUpdate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useTeams() {
  return useQuery({ queryKey: qk.teams, queryFn: () => unwrap(api.GET("/api/v1/teams")), staleTime: STALE.config });
}

export function useCreateTeam() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: TeamIn) => unwrap(api.POST("/api/v1/teams", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.teams }),
  });
}

export function useUpdateTeam() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: TeamUpdate }) =>
      unwrap(api.PATCH("/api/v1/teams/{team_id}", { params: { path: { team_id: id } }, body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.teams });
      void client.invalidateQueries({ queryKey: qk.projectsAll });
    },
  });
}

export function useDeleteTeam() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/teams/{team_id}", { params: { path: { team_id: id } } })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.teams });
      void client.invalidateQueries({ queryKey: qk.projectsAll });
    },
  });
}
