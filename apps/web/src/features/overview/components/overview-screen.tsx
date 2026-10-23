"use client";

import { PageHeader } from "@/components/page-header";
import { rangeLabel } from "@/lib/range";
import { useUiPrefs } from "@/lib/store";

import { useOverview } from "../api";
import { ActivityPanel } from "./activity-panel";
import { BreakdownPanel } from "./breakdown-panel";
import { BudgetHealth } from "./budget-health";
import { ConnectCard } from "./connect-card";
import { KpiGrid } from "./kpi-grid";
import { OpenAlerts } from "./open-alerts";

export function OverviewScreen() {
  const range = useUiPrefs((s) => s.range);
  const overview = useOverview(range);
  const noTraffic = overview.data && (overview.data.totals.requests ?? 0) === 0;

  return (
    <>
      <PageHeader
        title="Overview"
        description={`What every LLM call cost, what TokenShield saved and what it blocked. ${rangeLabel(range)}.`}
      />
      <div className="flex flex-col gap-4">
        <KpiGrid
          data={overview.data}
          range={range}
          loading={overview.isPending}
          error={overview.error}
          onRetry={() => void overview.refetch()}
        />
        {noTraffic && <ConnectCard />}
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ActivityPanel range={range} />
          </div>
          <BudgetHealth />
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <BreakdownPanel range={range} />
          </div>
          <OpenAlerts />
        </div>
      </div>
    </>
  );
}
