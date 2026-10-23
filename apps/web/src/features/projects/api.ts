"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Project, ProjectIn, ProjectUpdate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useProjects(includeArchived = false) {
  return useQuery({
    queryKey: qk.projects(includeArchived),
    queryFn: () => unwrap(api.GET("/api/v1/projects", { params: { query: { include_archived: includeArchived } } })),
    staleTime: STALE.config,
  });
}

export function useProject(id: string) {
  const client = useQueryClient();
  return useQuery({
    queryKey: qk.project(id),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}", { params: { path: { project_id: id } } })),
    staleTime: STALE.config,
    // Seed from the list when it is already cached, so the header renders instantly.
    initialData: () =>
      client.getQueryData<Project[]>(qk.projects(false))?.find((p) => p.id === id),
    initialDataUpdatedAt: () => client.getQueryState(qk.projects(false))?.dataUpdatedAt,
  });
}

export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectIn) => unwrap(api.POST("/api/v1/projects", { body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.projectsAll });
      void client.invalidateQueries({ queryKey: qk.teams });
      void client.invalidateQueries({ queryKey: qk.system });
    },
  });
}

export function useUpdateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ProjectUpdate }) =>
      unwrap(api.PATCH("/api/v1/projects/{project_id}", { params: { path: { project_id: id } }, body })),
    onSuccess: (project) => {
      client.setQueryData(qk.project(project.id), project);
      void client.invalidateQueries({ queryKey: qk.projectsAll });
      void client.invalidateQueries({ queryKey: qk.teams });
    },
  });
}
