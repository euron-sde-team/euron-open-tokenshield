"use client";

import * as React from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART, ChartLegend, ChartTooltipCard } from "@/components/charts/chart-tooltip";
import type { RangeKey, SeriesPoint } from "@/lib/api/types";
import { formatNumber, formatUsd, formatUsdAxis, formatTokens } from "@/lib/format";
import { formatBucket, formatBucketLong } from "@/lib/range";

export type ActivityMetric = "spend" | "requests";

interface Row {
  t: string;
  spend: number;
  avoided: number;
  hits: number;
  upstream: number;
  rejected: number;
  requests: number;
}

function toRows(points: SeriesPoint[]): Row[] {
  return points.map((p) => ({
    t: p.t,
    spend: p.cost_usd,
    avoided: p.avoided_usd,
    hits: p.cache_hits,
    rejected: p.rejected,
    upstream: Math.max(0, p.requests - p.cache_hits - p.rejected),
    requests: p.requests,
  }));
}

const axisProps = {
  stroke: CHART.axis,
  tick: { fill: CHART.axis, fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

/**
 * Spend vs spend avoided (two areas on one dollar axis), or requests split into cache
 * hits, upstream calls and rejections (stacked bars). One axis each, never dual.
 */
export default function ActivityChart({ points, range, metric }: { points: SeriesPoint[]; range: RangeKey; metric: ActivityMetric }) {
  const rows = React.useMemo(() => toRows(points), [points]);
  const ticks = React.useMemo(() => {
    const n = rows.length;
    if (n <= 8) return rows.map((r) => r.t);
    const step = Math.ceil(n / 7);
    return rows.filter((_, i) => i % step === 0).map((r) => r.t);
  }, [rows]);

  const totals = React.useMemo(
    () =>
      rows.reduce(
        (a, r) => ({ spend: a.spend + r.spend, avoided: a.avoided + r.avoided, hits: a.hits + r.hits, upstream: a.upstream + r.upstream, rejected: a.rejected + r.rejected }),
        { spend: 0, avoided: 0, hits: 0, upstream: 0, rejected: 0 },
      ),
    [rows],
  );

  return (
    <div className="flex flex-1 flex-col gap-3">
      {metric === "spend" ? (
        <ChartLegend
          items={[
            { label: "Spend", color: CHART.spend, value: formatUsd(totals.spend) },
            { label: "Spend avoided", color: CHART.avoided, value: formatUsd(totals.avoided) },
          ]}
        />
      ) : (
        <ChartLegend
          items={[
            { label: "Cache hits", color: CHART.avoided, value: formatTokens(totals.hits) },
            { label: "Upstream", color: CHART.spend, value: formatTokens(totals.upstream) },
            { label: "Rejected", color: CHART.rejected, value: formatTokens(totals.rejected) },
          ]}
        />
      )}
      <div className="min-h-[260px] w-full flex-1" role="img" aria-label={metric === "spend" ? "Spend and spend avoided over time" : "Requests over time"}>
        <ResponsiveContainer width="100%" height="100%">
          {metric === "spend" ? (
            <AreaChart data={rows} margin={{ top: 6, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="fill-spend" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART.spend} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={CHART.spend} stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="fill-avoided" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART.avoided} stopOpacity={0.22} />
                  <stop offset="100%" stopColor={CHART.avoided} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke={CHART.grid} />
              <XAxis dataKey="t" ticks={ticks} tickFormatter={(t: string) => formatBucket(t, range)} {...axisProps} minTickGap={16} />
              <YAxis tickFormatter={formatUsdAxis} width={52} {...axisProps} />
              <Tooltip
                cursor={{ stroke: CHART.axis, strokeDasharray: "3 3" }}
                content={({ active, payload }) => {
                  const row = payload?.[0]?.payload as Row | undefined;
                  if (!active || !row) return null;
                  return (
                    <ChartTooltipCard
                      title={formatBucketLong(row.t, range)}
                      rows={[
                        { label: "Spend", value: formatUsd(row.spend), color: CHART.spend },
                        { label: "Avoided", value: formatUsd(row.avoided), color: CHART.avoided },
                      ]}
                      footer={`${formatNumber(row.requests)} requests`}
                    />
                  );
                }}
              />
              <Area type="monotone" dataKey="spend" stroke={CHART.spend} strokeWidth={2} fill="url(#fill-spend)" activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }} />
              <Area type="monotone" dataKey="avoided" stroke={CHART.avoided} strokeWidth={2} fill="url(#fill-avoided)" activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }} />
            </AreaChart>
          ) : (
            <BarChart data={rows} margin={{ top: 6, right: 4, bottom: 0, left: 0 }} barCategoryGap="18%">
              <CartesianGrid vertical={false} stroke={CHART.grid} />
              <XAxis dataKey="t" ticks={ticks} tickFormatter={(t: string) => formatBucket(t, range)} {...axisProps} minTickGap={16} />
              <YAxis tickFormatter={(v: number) => formatTokens(v)} width={44} {...axisProps} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: "var(--muted)", opacity: 0.6 }}
                content={({ active, payload }) => {
                  const row = payload?.[0]?.payload as Row | undefined;
                  if (!active || !row) return null;
                  return (
                    <ChartTooltipCard
                      title={formatBucketLong(row.t, range)}
                      rows={[
                        { label: "Cache hits", value: formatNumber(row.hits), color: CHART.avoided },
                        { label: "Upstream", value: formatNumber(row.upstream), color: CHART.spend },
                        { label: "Rejected", value: formatNumber(row.rejected), color: CHART.rejected },
                      ]}
                      footer={`${formatNumber(row.requests)} total`}
                    />
                  );
                }}
              />
              <Bar dataKey="hits" stackId="r" fill={CHART.avoided} stroke="var(--card)" strokeWidth={1} />
              <Bar dataKey="upstream" stackId="r" fill={CHART.spend} stroke="var(--card)" strokeWidth={1} />
              <Bar dataKey="rejected" stackId="r" fill={CHART.rejected} stroke="var(--card)" strokeWidth={1} radius={[3, 3, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
