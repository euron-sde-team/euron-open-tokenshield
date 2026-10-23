"use client";

import { CoinsIcon, DatabaseZapIcon, LayersIcon, PiggyBankIcon, Trash2Icon, ZapIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Field } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import { useProjects } from "@/features/projects/api";
import { errorMessage } from "@/lib/api/errors";
import type { CacheEntry } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatNumber, formatRelative, formatTokens, formatUsd } from "@/lib/format";
import type { GlossaryKey } from "@/lib/glossary";

import { useCacheEntries, useCacheStats, useInvalidateEntry, usePurgeCache } from "../api";

function Stat({ icon: Icon, label, value, tone, hint }: { icon: typeof ZapIcon; label: string; value: string; tone?: "savings"; hint?: GlossaryKey }) {
  return (
    <div className="surface flex items-center gap-3 p-4">
      <span className={cn("flex size-9 items-center justify-center rounded-xl", tone === "savings" ? "bg-savings-soft text-savings" : "bg-primary-soft text-primary")}>
        <Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-1 text-[12px] text-muted-foreground">
          {label}
          {hint && <Hint term={hint} />}
        </div>
        <div className={cn("text-[20px] leading-tight font-semibold tabular", tone === "savings" && "text-savings")}>{value}</div>
      </div>
    </div>
  );
}

export function CacheScreen() {
  const stats = useCacheStats();
  const [projectId, setProjectId] = React.useState("");
  const entries = useCacheEntries(projectId || undefined);
  const projects = useProjects();
  const invalidate = useInvalidateEntry();
  const purge = usePurgeCache();
  const { canWrite } = usePermissions();
  const [target, setTarget] = React.useState<CacheEntry | null>(null);
  const [purgeOpen, setPurgeOpen] = React.useState(false);
  const [purgeScope, setPurgeScope] = React.useState("");

  const projectOptions = [{ value: "", label: "All projects" }, ...(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))];
  const purgeName = purgeScope ? projects.data?.find((p) => p.id === purgeScope)?.name : null;

  return (
    <>
      <PageHeader
        title="Cache"
        description={
          <>
            Answers reused instead of paid for. Entries never cross projects, and requests marked sensitive bypass the cache{" "}
            <Hint term="cacheScope" className="inline-flex align-text-bottom" />
          </>
        }
        actions={
          canWrite && (
            <Button variant="destructive-soft" onClick={() => setPurgeOpen(true)}>
              <Trash2Icon />
              Purge cache
            </Button>
          )
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.isPending ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[76px] rounded-[14px]" />)
        ) : stats.isError && !stats.data ? (
          <div className="surface col-span-full">
            <ErrorState error={stats.error} onRetry={() => void stats.refetch()} compact />
          </div>
        ) : (
          <>
            <Stat icon={LayersIcon} label="Active entries" value={`${formatNumber(stats.data.entries_active)} of ${formatNumber(stats.data.entries_total)}`} />
            <Stat icon={ZapIcon} label="Hits served" value={formatNumber(stats.data.hits_total)} />
            <Stat icon={CoinsIcon} label="Tokens saved" value={formatTokens(stats.data.tokens_saved)} />
            <Stat icon={PiggyBankIcon} label="Spend avoided" value={formatUsd(stats.data.avoided_cost_usd)} tone="savings" hint="spendAvoided" />
          </>
        )}
      </div>

      <Surface className="overflow-hidden">
        <SurfaceHeader
          title="Most valuable entries"
          description="Ranked by spend avoided"
          action={<SimpleSelect aria-label="Filter by project" size="sm" className="w-44" value={projectId} onValueChange={setProjectId} options={projectOptions} />}
        />
        {entries.isPending ? (
          <TableSkeleton rows={6} cols={5} />
        ) : entries.isError && !entries.data ? (
          <ErrorState error={entries.error} onRetry={() => void entries.refetch()} />
        ) : !entries.data?.length ? (
          <EmptyState
            icon={DatabaseZapIcon}
            title={projectId ? "Nothing cached for this project" : "The cache is empty"}
            description="Eligible responses are stored after their first upstream call. Repeat a temperature 0 request in the Playground to see a hit land here."
            action={
              projectId ? (
                <Button variant="outline" size="sm" onClick={() => setProjectId("")}>
                  Show all projects
                </Button>
              ) : undefined
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Prompt</TableHead>
                <TableHead className="hidden md:table-cell">Project</TableHead>
                <TableHead className="text-right">Hits</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Tokens saved</TableHead>
                <TableHead className="text-right">Avoided</TableHead>
                <TableHead className="hidden lg:table-cell">Expires</TableHead>
                {canWrite && <TableHead className="text-right"><span className="sr-only">Actions</span></TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...entries.data]
                .sort((a, b) => b.avoided_cost_usd - a.avoided_cost_usd)
                .map((e) => (
                  <TableRow key={e.key_hash} className={cn(e.active === false && "opacity-55")}>
                    <TableCell className="max-w-[320px]">
                      <div className="truncate">{e.prompt_excerpt ?? <span className="text-faint">Content not stored</span>}</div>
                      <div className="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-subtle">
                        <span className="font-mono">{e.model_alias}</span>
                        <span className="font-mono">{e.key_hash.slice(0, 10)}</span>
                        {e.kind !== "exact" && <Chip tone="info">{e.kind}</Chip>}
                        {e.active === false && <Chip tone="neutral">Expired</Chip>}
                      </div>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">{e.project_name ?? "n/a"}</TableCell>
                    <TableCell className="text-right tabular">
                      <div>{formatNumber(e.hits)}</div>
                      <div className="text-[11px] text-subtle">{formatRelative(e.last_hit_at)}</div>
                    </TableCell>
                    <TableCell className="hidden text-right tabular sm:table-cell">{formatTokens(e.tokens_saved)}</TableCell>
                    <TableCell className="text-right font-semibold text-savings tabular">{formatUsd(e.avoided_cost_usd)}</TableCell>
                    <TableCell className="hidden text-muted-foreground lg:table-cell">{formatRelative(e.expires_at)}</TableCell>
                    {canWrite && (
                      <TableCell className="text-right">
                        <Button variant="subtle" size="xs" onClick={() => setTarget(e)}>
                          Invalidate
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        )}
      </Surface>

      <ConfirmDialog
        open={!!target}
        onOpenChange={(o) => !o && setTarget(null)}
        title="Invalidate this entry?"
        description="The next identical request goes upstream and is cached again. Use this after a prompt's correct answer changes."
        confirmLabel="Invalidate"
        pending={invalidate.isPending}
        onConfirm={() =>
          target &&
          invalidate.mutate(target.key_hash, {
            onSuccess: () => {
              toast.success("Entry invalidated.");
              setTarget(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
      <ConfirmDialog
        open={purgeOpen}
        onOpenChange={setPurgeOpen}
        title={purgeName ? `Purge the cache for ${purgeName}?` : "Purge the entire cache?"}
        description="Every matching entry is removed now. The next requests go upstream and are paid for until the cache warms again."
        confirmLabel={purgeName ? "Purge project cache" : "Purge everything"}
        pending={purge.isPending}
        onConfirm={() =>
          purge.mutate(purgeScope || null, {
            onSuccess: (r) => {
              toast.success(r.message ?? "Cache purged.");
              setPurgeOpen(false);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      >
        <Field label="Scope" htmlFor="purge-scope">
          <SimpleSelect
            id="purge-scope"
            value={purgeScope}
            onValueChange={setPurgeScope}
            options={[{ value: "", label: "All projects" }, ...(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))]}
          />
        </Field>
      </ConfirmDialog>
    </>
  );
}
