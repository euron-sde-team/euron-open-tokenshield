"use client";

import { BotIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { buttonVariants } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTasks } from "@/features/overview/api";
import { ruleLabel } from "@/lib/chips";
import { formatDuration, formatNumber, formatRelative, formatUsd } from "@/lib/format";
import { rangeLabel } from "@/lib/range";
import { useUiPrefs } from "@/lib/store";

export function AgentsScreen() {
  const range = useUiPrefs((s) => s.range);
  const q = useTasks(range);
  const totals = React.useMemo(
    () =>
      (q.data ?? []).reduce(
        (a, t) => ({ tasks: a.tasks + 1, calls: a.calls + t.calls, cost: a.cost + t.cost_usd, stopped: a.stopped + (t.rejected > 0 ? 1 : 0) }),
        { tasks: 0, calls: 0, cost: 0, stopped: 0 },
      ),
    [q.data],
  );

  return (
    <>
      <PageHeader
        title="Agents"
        description={
          <>
            Multi-step agent runs grouped by the <code className="rounded bg-muted px-1 font-mono text-[12px]">x-tokenshield-task-id</code> header. Agent task
            caps stop a loop at its call, cost, repetition or time limit. {rangeLabel(range)}.
          </>
        }
      />
      {q.data?.length ? (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            { label: "Tasks", value: formatNumber(totals.tasks) },
            { label: "Model calls", value: formatNumber(totals.calls) },
            { label: "Agent spend", value: formatUsd(totals.cost) },
            { label: "Tasks stopped by a rule", value: formatNumber(totals.stopped), warn: totals.stopped > 0 },
          ].map((s) => (
            <div key={s.label} className="rounded-xl bg-card px-4 py-3 shadow-[var(--elev-1)]">
              <div className="text-[12px] text-muted-foreground">{s.label}</div>
              <div className={`mt-0.5 text-[20px] font-semibold tabular ${s.warn ? "text-warning" : ""}`}>{s.value}</div>
            </div>
          ))}
        </div>
      ) : null}
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={8} cols={6} />
          </div>
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : !q.data?.length ? (
          <EmptyState
            icon={BotIcon}
            title="No agent tasks in this range"
            description="Send x-tokenshield-task-id with each call an agent makes for one job. TokenShield then tracks the run as a whole and can stop it when it loops."
            action={
              <Link href="/policies" className={buttonVariants({ size: "sm" })}>
                Set agent task caps
              </Link>
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Task</TableHead>
                <TableHead className="hidden md:table-cell">Project</TableHead>
                <TableHead className="text-right">Calls</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead className="text-right">Rejected</TableHead>
                <TableHead className="hidden lg:table-cell">Last rule</TableHead>
                <TableHead className="hidden sm:table-cell">Duration</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.map((t) => (
                <TableRow key={t.task_id}>
                  <TableCell>
                    <Link href={`/requests?task_id=${encodeURIComponent(t.task_id)}`} className="font-mono text-[12.5px] font-medium hover:text-primary hover:underline">
                      {t.task_id}
                    </Link>
                    <div className="text-[11px] text-subtle">last call {formatRelative(t.last_at)}</div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">{t.project_name ?? "n/a"}</TableCell>
                  <TableCell className="text-right tabular">{formatNumber(t.calls)}</TableCell>
                  <TableCell className="text-right tabular">{formatUsd(t.cost_usd)}</TableCell>
                  <TableCell className="text-right tabular">
                    {t.rejected > 0 ? <span className="font-semibold text-warning">{formatNumber(t.rejected)}</span> : <span className="text-faint">0</span>}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell">{t.last_rule ? <Chip tone="warning">{ruleLabel(t.last_rule)}</Chip> : <span className="text-faint">None</span>}</TableCell>
                  <TableCell className="hidden text-muted-foreground tabular sm:table-cell">
                    {formatDuration(Math.max(0, Math.round((new Date(t.last_at).getTime() - new Date(t.first_at).getTime()) / 1000)))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Surface>
    </>
  );
}
