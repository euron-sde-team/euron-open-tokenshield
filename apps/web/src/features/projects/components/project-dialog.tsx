"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { useTeams } from "@/features/teams/api";
import { errorMessage } from "@/lib/api/errors";

import { useCreateProject } from "../api";

export function ProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const teams = useTeams();
  const create = useCreateProject();
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [teamId, setTeamId] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setName("");
      setDescription("");
      setTeamId("");
      setError(null);
    }
  }, [open]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Name the project after the app or service that will call the gateway.");
      return;
    }
    create.mutate(
      { name: name.trim(), description: description.trim(), team_id: teamId || null, cache_enabled: true, cache_ttl_s: 3600 },
      {
        onSuccess: (p) => {
          toast.success(`Project "${p.name}" created. Next: give it an API key.`);
          onOpenChange(false);
          router.push(`/projects/${p.id}`);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>A project is one application or service. Keys, budgets, cache and spend are tracked per project.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <Field label="Name" htmlFor="project-name">
              <Input id="project-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Support Copilot" />
            </Field>
            <Field label="Description" htmlFor="project-desc" hint="Optional. Shown on the project page.">
              <Textarea id="project-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
            <Field label="Team" htmlFor="project-team" hint="Optional. Team budgets cover all of a team's projects.">
              <SimpleSelect
                id="project-team"
                value={teamId}
                onValueChange={setTeamId}
                placeholder="No team"
                options={[{ value: "", label: "No team" }, ...(teams.data ?? []).map((t) => ({ value: t.id, label: t.name }))]}
              />
            </Field>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating..." : "Create project"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
