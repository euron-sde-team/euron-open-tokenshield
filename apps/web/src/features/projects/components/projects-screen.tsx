"use client";

import { BoxesIcon, ChevronRightIcon, DatabaseZapIcon, KeyRoundIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { useBreakdown } from "@/features/overview/api";
import { formatDuration, formatNumber, formatUsd } from "@/lib/format";
import { rangeLabel } from "@/lib/range";
import { useUiPrefs } from "@/lib/store";

import { useProjects } from "../api";
import { ProjectDialog } from "./project-dialog";

export function ProjectsScreen() {
  const q = useProjects();
  const range = useUiPrefs((s) => s.range);
  const spend = useBreakdown("project", range);
  const { canWrite } = usePermissions();
  const [open, setOpen] = React.useState(false);
  const spendById = React.useMemo(() => new Map((spend.data ?? []).map((r) => [r.key, r])), [spend.data]);

  const newButton = canWrite && (
    <Button onClick={() => setOpen(true)}>
      <PlusIcon />
      New project
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Projects"
        description="Each application or service that calls the gateway. Spend, keys, cache and model access are set per project."
        actions={newButton}
      />
      {q.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44 rounded-[14px]" />
          ))}
        </div>
      ) : q.isError && !q.data ? (
        <div className="surface">
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        </div>
      ) : !q.data?.length ? (
        <div className="surface">
          <EmptyState
            icon={BoxesIcon}
            title="No projects yet"
            description="Create a project for each app that will call an LLM. Its keys, budgets and spend roll up here."
            action={newButton || undefined}
          />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {q.data.map((p) => {
            const s = spendById.get(p.id);
            return (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="surface group flex flex-col gap-4 p-4 transition-shadow outline-none hover:shadow-[var(--elev-3)] focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-[14px] font-semibold group-hover:text-primary">{p.name}</h3>
                    <p className="mt-0.5 line-clamp-2 text-[12.5px] leading-relaxed text-muted-foreground">{p.description || "No description"}</p>
                  </div>
                  <ChevronRightIcon className="size-4 shrink-0 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {p.team_name && <Chip tone="primary">{p.team_name}</Chip>}
                  <Chip tone="neutral">
                    <KeyRoundIcon />
                    {p.key_count ?? 0} key{p.key_count === 1 ? "" : "s"}
                  </Chip>
                  <Chip tone={p.cache_enabled ? "savings" : "neutral"}>
                    <DatabaseZapIcon />
                    {p.cache_enabled ? `Cache ${formatDuration(p.cache_ttl_s)}` : "Cache off"}
                  </Chip>
                  {p.allowed_models?.length ? <Chip tone="warning">{p.allowed_models.length} models allowed</Chip> : null}
                </div>
                <div className="mt-auto grid grid-cols-3 gap-2 rounded-xl bg-muted/60 px-3 py-2.5">
                  <div>
                    <div className="text-[11px] text-subtle">Spend</div>
                    <div className="text-[14px] font-semibold tabular">{s ? formatUsd(s.cost_usd) : spend.isPending ? "..." : "$0.00"}</div>
                  </div>
                  <div>
                    <div className="text-[11px] text-subtle">Avoided</div>
                    <div className="text-[14px] font-semibold text-savings tabular">{s ? formatUsd(s.avoided_usd) : "$0.00"}</div>
                  </div>
                  <div>
                    <div className="text-[11px] text-subtle">Requests</div>
                    <div className="text-[14px] font-semibold tabular">{s ? formatNumber(s.requests) : "0"}</div>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
      {q.data?.length ? <p className="mt-4 text-xs text-muted-foreground">Spend figures: {rangeLabel(range).toLowerCase()}.</p> : null}
      <ProjectDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
