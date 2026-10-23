"use client";

import { PieChartIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Skeleton } from "@/components/ui/skeleton";
import type { BreakdownBy, BreakdownRow, RangeKey } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatNumber, formatRatio, formatTokens, formatUsd } from "@/lib/format";

import { useBreakdown } from "../api";

const TABS: { by: BreakdownBy; label: string }[] = [
  { by: "model", label: "Model" },
  { by: "project", label: "Project" },
  { by: "provider", label: "Provider" },
  { by: "api_key", label: "Key" },
];

/** Ranked horizontal bars: one hue (magnitude), the value printed beside each bar. */
export function BreakdownList({ rows, by, linkProjects = true }: { rows: BreakdownRow[]; by: BreakdownBy; linkProjects?: boolean }) {
  const max = Math.max(...rows.map((r) => r.cost_usd), 0);
  return (
    <ul className="space-y-3.5">
      {rows.slice(0, 8).map((r) => {
        const width = max > 0 ? Math.max(1.5, (r.cost_usd / max) * 100) : 0;
        const label =
          by === "project" && linkProjects ? (
            <Link href={`/projects/${r.key}`} className="truncate font-medium text-foreground hover:text-primary hover:underline">
              {r.label}
            </Link>
          ) : (
            <span className={cn("truncate font-medium text-foreground", by === "model" && "font-mono text-[12.5px]")}>{r.label}</span>
          );
        return (
          <li key={r.key} className="group">
            <div className="flex items-baseline justify-between gap-3 text-[13px]">
              <div className="flex min-w-0 items-baseline gap-2">
                {label}
                <span className="shrink-0 text-[11.5px] text-subtle tabular">{formatNumber(r.requests)} req</span>
              </div>
              <div className="flex shrink-0 items-baseline gap-2 tabular">
                <span className="font-semibold text-foreground">{formatUsd(r.cost_usd)}</span>
                <span className="w-11 text-right text-[11.5px] text-subtle">{formatRatio(r.share, 0)}</span>
              </div>
            </div>
            <div className="mt-1.5 h-1.5 w-full rounded-full bg-muted" title={`${formatTokens(r.input_tokens)} in, ${formatTokens(r.output_tokens)} out, ${formatUsd(r.avoided_usd)} avoided`}>
              <div className="h-full rounded-full bg-[var(--chart-spend)] transition-[width] duration-500" style={{ width: `${width}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function BreakdownPanel({ range, projectId, tabs = TABS }: { range: RangeKey; projectId?: string; tabs?: typeof TABS }) {
  const [by, setBy] = React.useState<BreakdownBy>(tabs[0]?.by ?? "model");
  const q = useBreakdown(by, range, projectId);
  return (
    <Surface className="flex h-full flex-col">
      <SurfaceHeader
        title="Where the money goes"
        description="Spend and share by dimension"
        action={
          <div role="tablist" aria-label="Breakdown dimension" className="inline-flex gap-0.5 rounded-lg bg-muted p-0.5">
            {tabs.map((t) => (
              <button
                key={t.by}
                role="tab"
                type="button"
                aria-selected={by === t.by}
                onClick={() => setBy(t.by)}
                className={cn(
                  "h-7 rounded-md px-2.5 text-[12px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
                  by === t.by && "bg-card text-foreground shadow-[var(--elev-1)] dark:bg-accent",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        }
      />
      <div className="flex-1 px-5 pb-5">
        {q.isPending ? (
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-1.5">
                <Skeleton className="h-3.5 w-2/3" />
                <Skeleton className="h-1.5 w-full" />
              </div>
            ))}
          </div>
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} compact />
        ) : !q.data?.length ? (
          <EmptyState compact icon={PieChartIcon} title="Nothing to break down yet" description="Once requests flow, spend splits by model, project, provider and key here." />
        ) : (
          <BreakdownList rows={q.data} by={by} />
        )}
      </div>
    </Surface>
  );
}
