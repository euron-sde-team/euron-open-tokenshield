"use client";

import { BanIcon, DatabaseZapIcon, DollarSignIcon, PiggyBankIcon, TimerIcon, ZapIcon } from "lucide-react";

import { ErrorState } from "@/components/error-state";
import { KpiTile } from "@/components/kpi-tile";
import type { Overview, RangeKey, Totals } from "@/lib/api/types";
import { formatLatency, formatNumber, formatRatio, formatUsd } from "@/lib/format";
import { previousPeriodLabel } from "@/lib/range";

export function KpiGrid({
  data,
  range,
  loading,
  error,
  onRetry,
}: {
  data: Overview | undefined;
  range: RangeKey;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  if (error && !data) {
    return (
      <div className="surface">
        <ErrorState error={error} onRetry={onRetry} title="Could not load the headline numbers" compact />
      </div>
    );
  }
  const t: Partial<Totals> = data?.totals ?? {};
  const p: Partial<Totals> = data?.previous ?? {};
  const cmp = previousPeriodLabel(range);
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <KpiTile label="Spend" icon={DollarSignIcon} value={formatUsd(t.cost_usd ?? 0)} current={t.cost_usd} previous={p.cost_usd} goodWhen="down" comparison={cmp} loading={loading} />
      <KpiTile label="Requests" icon={ZapIcon} value={formatNumber(t.requests ?? 0)} current={t.requests} previous={p.requests} goodWhen="neutral" comparison={cmp} loading={loading} />
      <KpiTile
        label="Cache hit rate"
        icon={DatabaseZapIcon}
        hint="cacheHitRate"
        accent="savings"
        value={formatRatio(t.cache_hit_rate ?? 0)}
        current={t.cache_hit_rate}
        previous={p.cache_hit_rate}
        goodWhen="up"
        comparison={cmp}
        loading={loading}
      />
      <KpiTile
        label="Avoided"
        icon={PiggyBankIcon}
        hint="spendAvoided"
        accent="savings"
        value={formatUsd(t.avoided_usd ?? 0)}
        current={t.avoided_usd}
        previous={p.avoided_usd}
        goodWhen="up"
        comparison={cmp}
        loading={loading}
      />
      <KpiTile
        label="Rejected"
        icon={BanIcon}
        hint="rejected"
        accent="warning"
        value={formatNumber(t.rejected ?? 0)}
        current={t.rejected}
        previous={p.rejected}
        goodWhen="neutral"
        comparison={cmp}
        loading={loading}
      />
      <KpiTile label="Avg latency" icon={TimerIcon} value={formatLatency(t.avg_latency_ms ?? 0)} current={t.avg_latency_ms} previous={p.avg_latency_ms} goodWhen="down" comparison={cmp} loading={loading} />
    </div>
  );
}
