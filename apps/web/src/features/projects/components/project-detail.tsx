"use client";

import { ArchiveIcon, ArrowLeftIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { Surface, SurfaceHeader } from "@/components/surface";
import { ToggleChips } from "@/components/toggle-chips";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { usePermissions } from "@/features/auth/api";
import { CreateKeyDialog } from "@/features/keys/components/create-key-dialog";
import { KeysTable } from "@/features/keys/components/keys-table";
import { useModels } from "@/features/models/api";
import { useOverview } from "@/features/overview/api";
import { ActivityPanel } from "@/features/overview/components/activity-panel";
import { BreakdownPanel } from "@/features/overview/components/breakdown-panel";
import { KpiGrid } from "@/features/overview/components/kpi-grid";
import { useTeams } from "@/features/teams/api";
import { errorMessage } from "@/lib/api/errors";
import type { Project } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useUiPrefs } from "@/lib/store";

import { useProject, useUpdateProject } from "../api";

const TTL_OPTIONS = [
  { value: "300", label: "5 minutes" },
  { value: "900", label: "15 minutes" },
  { value: "3600", label: "1 hour" },
  { value: "21600", label: "6 hours" },
  { value: "86400", label: "24 hours" },
  { value: "604800", label: "7 days" },
];

function SettingRow({ label, hint, children }: { label: React.ReactNode; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div className="min-w-0">
        <div className="text-[13px] font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function CacheSettings({ project, canWrite }: { project: Project; canWrite: boolean }) {
  const update = useUpdateProject();
  const [ttl, setTtl] = React.useState(String(project.cache_ttl_s));
  React.useEffect(() => setTtl(String(project.cache_ttl_s)), [project.cache_ttl_s]);
  const ttlOptions = TTL_OPTIONS.some((o) => o.value === ttl) ? TTL_OPTIONS : [...TTL_OPTIONS, { value: ttl, label: `${ttl} s` }];

  const save = (body: Parameters<typeof update.mutate>[0]["body"], msg: string) =>
    update.mutate({ id: project.id, body }, { onSuccess: () => toast.success(msg), onError: (e) => toast.error(errorMessage(e)) });

  return (
    <Surface className="h-full">
      <SurfaceHeader title="Cache" titleExtra={<Hint term="cacheScope" />} description="Identical eligible requests are answered without an upstream call." />
      <div className="divide-y divide-hairline px-5 pb-3">
        <SettingRow label="Response cache" hint="Exact-match cache, scoped to this project.">
          <Switch
            checked={project.cache_enabled}
            disabled={!canWrite || update.isPending}
            aria-label="Response cache"
            onCheckedChange={(v) => save({ cache_enabled: v }, v ? "Cache enabled." : "Cache disabled.")}
          />
        </SettingRow>
        <SettingRow label="Time to live" hint="How long an answer can be reused.">
          <SimpleSelect
            aria-label="Cache time to live"
            size="sm"
            className="w-32"
            value={ttl}
            disabled={!canWrite || !project.cache_enabled}
            options={ttlOptions}
            onValueChange={(v) => {
              setTtl(v);
              save({ cache_ttl_s: Number(v) }, "Cache TTL updated.");
            }}
          />
        </SettingRow>
        <SettingRow label={<span className="flex items-center gap-1.5">Cache non-deterministic <Hint term="nondeterministic" /></span>} hint="Also cache requests with temperature above 0.">
          <Switch
            checked={project.cache_nondeterministic}
            disabled={!canWrite || !project.cache_enabled}
            aria-label="Cache non-deterministic requests"
            onCheckedChange={(v) => save({ cache_nondeterministic: v }, "Saved.")}
          />
        </SettingRow>
        <SettingRow label="Semantic cache" hint="Reuse answers to close-enough prompts. Needs SEMANTIC_CACHE=true on the server.">
          <Switch
            checked={project.semantic_cache_enabled}
            disabled={!canWrite || !project.cache_enabled}
            aria-label="Semantic cache"
            onCheckedChange={(v) => save({ semantic_cache_enabled: v }, "Saved.")}
          />
        </SettingRow>
      </div>
    </Surface>
  );
}

function AccessSettings({ project, canWrite }: { project: Project; canWrite: boolean }) {
  const models = useModels();
  const teams = useTeams();
  const update = useUpdateProject();
  const [restrict, setRestrict] = React.useState(!!project.allowed_models);
  const [allowed, setAllowed] = React.useState<string[]>(project.allowed_models ?? []);
  const [teamId, setTeamId] = React.useState(project.team_id ?? "");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setRestrict(!!project.allowed_models);
    setAllowed(project.allowed_models ?? []);
    setTeamId(project.team_id ?? "");
  }, [project.allowed_models, project.team_id]);

  const dirty =
    restrict !== !!project.allowed_models ||
    (restrict && JSON.stringify([...allowed].sort()) !== JSON.stringify([...(project.allowed_models ?? [])].sort())) ||
    teamId !== (project.team_id ?? "");

  function save() {
    if (restrict && !allowed.length) {
      setError("Pick at least one model, or allow all models.");
      return;
    }
    setError(null);
    update.mutate(
      { id: project.id, body: { allowed_models: restrict ? allowed : null, team_id: teamId || null } },
      { onSuccess: () => toast.success("Access settings saved."), onError: (e) => setError(errorMessage(e)) },
    );
  }

  return (
    <Surface className="h-full">
      <SurfaceHeader title="Access" description="Ownership and which models this project may call." />
      <div className="space-y-4 px-5 pb-5">
        <Field label="Team" htmlFor="project-team">
          <SimpleSelect
            id="project-team"
            value={teamId}
            disabled={!canWrite}
            onValueChange={setTeamId}
            options={[{ value: "", label: "No team" }, ...(teams.data ?? []).map((t) => ({ value: t.id, label: t.name }))]}
          />
        </Field>
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-[13px] font-medium">Limit to specific models</div>
            <div className="text-xs text-muted-foreground">Off: every enabled, unrestricted model is allowed.</div>
          </div>
          <Switch checked={restrict} disabled={!canWrite} onCheckedChange={setRestrict} aria-label="Limit to specific models" />
        </div>
        {restrict && (
          <ToggleChips
            ariaLabel="Allowed models"
            disabled={!canWrite}
            options={(models.data ?? []).map((m) => ({ value: m.alias, label: m.alias }))}
            value={allowed}
            onChange={setAllowed}
          />
        )}
        {error && <FieldError>{error}</FieldError>}
        {canWrite && (
          <Button size="sm" disabled={!dirty || update.isPending} onClick={save}>
            {update.isPending ? "Saving..." : "Save access"}
          </Button>
        )}
      </div>
    </Surface>
  );
}

function RenameForm({ project, canWrite }: { project: Project; canWrite: boolean }) {
  const update = useUpdateProject();
  const [name, setName] = React.useState(project.name);
  const [archiveOpen, setArchiveOpen] = React.useState(false);
  React.useEffect(() => setName(project.name), [project.name]);
  if (!canWrite) return null;
  return (
    <Surface>
      <SurfaceHeader title="Project settings" />
      <div className="flex flex-col gap-4 px-5 pb-5 sm:flex-row sm:items-end">
        <Field label="Name" htmlFor="project-rename" className="flex-1">
          <Input id="project-rename" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={!name.trim() || name.trim() === project.name || update.isPending}
            onClick={() =>
              update.mutate({ id: project.id, body: { name: name.trim() } }, { onSuccess: () => toast.success("Renamed."), onError: (e) => toast.error(errorMessage(e)) })
            }
          >
            Rename
          </Button>
          <Button variant="destructive-soft" onClick={() => setArchiveOpen(true)}>
            <ArchiveIcon />
            {project.archived ? "Unarchive" : "Archive"}
          </Button>
        </div>
      </div>
      <ConfirmDialog
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
        title={project.archived ? `Unarchive "${project.name}"?` : `Archive "${project.name}"?`}
        description={
          project.archived
            ? "Its keys start working again."
            : "Its keys stop working and it disappears from pickers. History and spend stay intact, and you can unarchive later."
        }
        confirmLabel={project.archived ? "Unarchive" : "Archive project"}
        destructive={!project.archived}
        pending={update.isPending}
        onConfirm={() =>
          update.mutate(
            { id: project.id, body: { archived: !project.archived } },
            {
              onSuccess: () => {
                toast.success(project.archived ? "Project restored." : "Project archived.");
                setArchiveOpen(false);
              },
              onError: (e) => toast.error(errorMessage(e)),
            },
          )
        }
      />
    </Surface>
  );
}

export function ProjectDetail({ id }: { id: string }) {
  const q = useProject(id);
  const range = useUiPrefs((s) => s.range);
  const overview = useOverview(range, id);
  const { canWrite } = usePermissions();
  const [keyOpen, setKeyOpen] = React.useState(false);

  const back = (
    <Link href="/projects" className="inline-flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
      <ArrowLeftIcon className="size-3.5" />
      Projects
    </Link>
  );

  if (q.isPending) {
    return (
      <>
        <div className="mb-6 space-y-2">
          {back}
          <Skeleton className="h-7 w-56" />
          <Skeleton className="h-4 w-80" />
        </div>
        <Skeleton className="h-32 rounded-[14px]" />
      </>
    );
  }
  if (q.isError) {
    return (
      <>
        <div className="mb-4">{back}</div>
        <div className="surface">
          <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load this project" />
        </div>
      </>
    );
  }
  const p = q.data;
  return (
    <>
      <PageHeader
        eyebrow={back}
        title={
          <span className="flex flex-wrap items-center gap-2">
            {p.name}
            {p.archived && <Chip tone="neutral">Archived</Chip>}
          </span>
        }
        description={
          <>
            {[p.description || "No description", p.team_name ? `Team ${p.team_name}` : null, `Created ${formatDate(p.created_at)}`]
              .filter(Boolean)
              .map((part) => String(part).replace(/[.\s]+$/, ""))
              .join(" · ")}
          </>
        }
        actions={
          canWrite && (
            <Button onClick={() => setKeyOpen(true)}>
              <PlusIcon />
              New key
            </Button>
          )
        }
      />
      <div className="flex flex-col gap-4">
        <KpiGrid data={overview.data} range={range} loading={overview.isPending} error={overview.error} onRetry={() => void overview.refetch()} />
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ActivityPanel range={range} projectId={id} />
          </div>
          <BreakdownPanel range={range} projectId={id} tabs={[{ by: "model", label: "Model" }, { by: "api_key", label: "Key" }]} />
        </div>
        <Surface className="overflow-hidden">
          <SurfaceHeader title="API keys" description="Keys that bill to this project." />
          <KeysTable projectId={id} includeRevoked={false} canWrite={canWrite} onCreate={() => setKeyOpen(true)} showProject={false} />
        </Surface>
        <div className="grid gap-4 lg:grid-cols-2">
          <CacheSettings project={p} canWrite={canWrite} />
          <AccessSettings project={p} canWrite={canWrite} />
        </div>
        <RenameForm project={p} canWrite={canWrite} />
      </div>
      <CreateKeyDialog open={keyOpen} onOpenChange={setKeyOpen} projectId={id} />
    </>
  );
}
