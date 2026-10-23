import type { RangeKey } from "./api/types";

export const RANGES: readonly RangeKey[] = ["1h", "24h", "7d", "30d", "90d"] as const;
export const DEFAULT_RANGE: RangeKey = "30d";

const RANGE_MS: Record<RangeKey, number> = {
  "1h": 3_600_000,
  "24h": 86_400_000,
  "7d": 7 * 86_400_000,
  "30d": 30 * 86_400_000,
  "90d": 90 * 86_400_000,
};

const RANGE_LABEL: Record<RangeKey, string> = {
  "1h": "Last hour",
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 90 days",
};

const PREVIOUS_LABEL: Record<RangeKey, string> = {
  "1h": "vs prior hour",
  "24h": "vs prior 24h",
  "7d": "vs prior 7d",
  "30d": "vs prior 30d",
  "90d": "vs prior 90d",
};

export function isRangeKey(value: unknown): value is RangeKey {
  return typeof value === "string" && (RANGES as readonly string[]).includes(value);
}

export function rangeMs(range: RangeKey): number {
  return RANGE_MS[range];
}

export function rangeLabel(range: RangeKey): string {
  return RANGE_LABEL[range];
}

export function previousPeriodLabel(range: RangeKey): string {
  return PREVIOUS_LABEL[range];
}

/** The API buckets 1h and 24h by hour and longer ranges by day. */
export function bucketUnit(range: RangeKey): "hour" | "day" {
  return range === "1h" || range === "24h" ? "hour" : "day";
}

/** Start of the window for a range, relative to `now`. */
export function rangeStart(range: RangeKey, now: Date = new Date()): Date {
  return new Date(now.getTime() - RANGE_MS[range]);
}

const hourFmt = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
const dayFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const hourLongFmt = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dayLongFmt = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" });

/** Short axis label for a bucket timestamp. */
export function formatBucket(iso: string, range: RangeKey): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return bucketUnit(range) === "hour" ? hourFmt.format(d) : dayFmt.format(d);
}

/** Longer label for a tooltip header. */
export function formatBucketLong(iso: string, range: RangeKey): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return bucketUnit(range) === "hour" ? hourLongFmt.format(d) : dayLongFmt.format(d);
}
