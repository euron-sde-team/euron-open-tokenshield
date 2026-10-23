"use client";

import { ActivityIcon } from "lucide-react";
import dynamic from "next/dynamic";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Skeleton } from "@/components/ui/skeleton";
import type { RangeKey } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { rangeLabel } from "@/lib/range";

import { useTimeseries } from "../api";
import type { ActivityMetric } from "./activity-chart";

// Recharts is the heaviest dependency on the page; load it in its own chunk.
const ActivityChart = dynamic(() => import("./activity-chart"), {
  ssr: false,
  loading: () => <Skeleton className="h-[286px] w-full rounded-xl" />,
});

export function ActivityPanel({ range, projectId }: { range: RangeKey; projectId?: string }) {
  const series = useTimeseries(range, projectId);
  const [metric, setMetric] = React.useState<ActivityMetric>("spend");
  const empty = series.data && series.data.every((p) => p.requests === 0);

  return (
    <Surface className="flex h-full flex-col">
      <SurfaceHeader
        title={metric === "spend" ? "Spend vs spend avoided" : "Requests by outcome"}
        description={`${rangeLabel(range)}, ${range === "1h" || range === "24h" ? "hourly" : "daily"}`}
        titleExtra={null}
        action={
          <div role="tablist" aria-label="Chart metric" className="inline-flex gap-0.5 rounded-lg bg-muted p-0.5">
            {(["spend", "requests"] as const).map((m) => (
              <button
                key={m}
                role="tab"
                type="button"
                aria-selected={metric === m}
                onClick={() => setMetric(m)}
                className={cn(
                  "h-7 rounded-md px-2.5 text-[12px] font-medium text-muted-foreground capitalize transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
                  metric === m && "bg-card text-foreground shadow-[var(--elev-1)] dark:bg-accent",
                )}
              >
                {m}
              </button>
            ))}
          </div>
        }
      />
      <div className="flex flex-1 flex-col px-5 pb-5">
        {series.isPending ? (
          <Skeleton className="h-[286px] w-full rounded-xl" />
        ) : series.isError && !series.data ? (
          <ErrorState error={series.error} onRetry={() => void series.refetch()} compact />
        ) : empty ? (
          <EmptyState
            compact
            icon={ActivityIcon}
            title="No traffic in this range"
            description="Requests appear here within a minute of passing through the gateway. Pick a longer range or send one from the Playground."
          />
        ) : (
          <ActivityChart points={series.data ?? []} range={range} metric={metric} />
        )}
      </div>
    </Surface>
  );
}
