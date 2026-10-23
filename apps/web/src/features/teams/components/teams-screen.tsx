"use client";

import { MoreHorizontalIcon, PencilIcon, PlusIcon, Trash2Icon, UsersRoundIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input, Textarea } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { useProjects } from "@/features/projects/api";
import { errorMessage } from "@/lib/api/errors";
import type { Team } from "@/lib/api/types";
import { initials } from "@/lib/format";

import { useCreateTeam, useDeleteTeam, useTeams, useUpdateTeam } from "../api";

function TeamDialog({ open, onOpenChange, team }: { open: boolean; onOpenChange: (o: boolean) => void; team: Team | null }) {
  const create = useCreateTeam();
  const update = useUpdateTeam();
  const pending = create.isPending || update.isPending;
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (open) {
      setName(team?.name ?? "");
      setDescription(team?.description ?? "");
      setError(null);
    }
  }, [open, team]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("Name the team.");
    const done = {
      onSuccess: () => {
        toast.success(team ? "Team updated." : "Team created.");
        onOpenChange(false);
      },
      onError: (err: unknown) => setError(errorMessage(err)),
    };
    if (team) update.mutate({ id: team.id, body: { name: name.trim(), description: description.trim() } }, done);
    else create.mutate({ name: name.trim(), description: description.trim() }, done);
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{team ? "Edit team" : "New team"}</DialogTitle>
          <DialogDescription>Teams group projects so spend can be budgeted and reported per team.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <Field label="Name" htmlFor="team-name">
              <Input id="team-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Platform" />
            </Field>
            <Field label="Description" htmlFor="team-desc">
              <Textarea id="team-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Saving..." : team ? "Save" : "Create team"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function TeamsScreen() {
  const q = useTeams();
  const projects = useProjects();
  const del = useDeleteTeam();
  const { canWrite } = usePermissions();
  const [dialog, setDialog] = React.useState<{ open: boolean; team: Team | null }>({ open: false, team: null });
  const [toDelete, setToDelete] = React.useState<Team | null>(null);

  const newButton = canWrite && (
    <Button onClick={() => setDialog({ open: true, team: null })}>
      <PlusIcon />
      New team
    </Button>
  );

  return (
    <>
      <PageHeader title="Teams" description="Groups of projects. Team budgets cap everything the team's projects spend together." actions={newButton} />
      {q.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-[14px]" />
          ))}
        </div>
      ) : q.isError && !q.data ? (
        <div className="surface">
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        </div>
      ) : !q.data?.length ? (
        <div className="surface">
          <EmptyState
            icon={UsersRoundIcon}
            title="No teams yet"
            description="Create a team per group that owns LLM features, then assign projects to it for team-level budgets and reports."
            action={newButton || undefined}
          />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {q.data.map((t) => {
            const teamProjects = (projects.data ?? []).filter((p) => p.team_id === t.id);
            return (
              <article key={t.id} className="surface flex flex-col gap-3 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-[12px] font-semibold text-primary">
                      {initials(t.name)}
                    </span>
                    <div className="min-w-0">
                      <h3 className="truncate text-[14px] font-semibold">{t.name}</h3>
                      <p className="truncate text-[12.5px] text-muted-foreground">{t.description || "No description"}</p>
                    </div>
                  </div>
                  {canWrite && (
                    <DropdownMenu>
                      <DropdownMenuTrigger render={<Button variant="subtle" size="icon-xs" aria-label={`Actions for ${t.name}`} />}>
                        <MoreHorizontalIcon />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent className="min-w-40">
                        <DropdownMenuItem onClick={() => setDialog({ open: true, team: t })}>
                          <PencilIcon />
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem variant="destructive" onClick={() => setToDelete(t)}>
                          <Trash2Icon />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
                <div className="mt-auto rounded-xl bg-muted/60 px-3 py-2.5">
                  <div className="mb-1.5 text-[11px] text-subtle">
                    {t.project_count ?? teamProjects.length} project{(t.project_count ?? teamProjects.length) === 1 ? "" : "s"}
                  </div>
                  {teamProjects.length ? (
                    <div className="flex flex-wrap gap-1.5">
                      {teamProjects.map((p) => (
                        <Link key={p.id} href={`/projects/${p.id}`} className="rounded-md bg-card px-2 py-0.5 text-[12px] shadow-[var(--elev-1)] hover:text-primary dark:bg-accent">
                          {p.name}
                        </Link>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[12px] text-muted-foreground">Assign projects to this team from a project&apos;s Access settings.</p>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
      <TeamDialog open={dialog.open} team={dialog.team} onOpenChange={(open) => setDialog((d) => ({ ...d, open }))} />
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`Delete team "${toDelete?.name ?? ""}"?`}
        description="Its projects stay, without a team. Budgets scoped to this team stop applying."
        confirmLabel="Delete team"
        pending={del.isPending}
        onConfirm={() =>
          toDelete &&
          del.mutate(toDelete.id, {
            onSuccess: () => {
              toast.success("Team deleted.");
              setToDelete(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </>
  );
}
