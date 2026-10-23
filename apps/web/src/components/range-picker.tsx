"use client";

import { cn } from "@/lib/cn";
import { RANGES, rangeLabel } from "@/lib/range";
import { useUiPrefs } from "@/lib/store";

/** Segmented 1h / 24h / 7d / 30d / 90d control bound to the persisted range. */
export function RangePicker({ className }: { className?: string }) {
  const range = useUiPrefs((s) => s.range);
  const setRange = useUiPrefs((s) => s.setRange);
  return (
    <div role="radiogroup" aria-label="Time range" className={cn("inline-flex items-center gap-0.5 rounded-lg bg-muted p-0.5", className)}>
      {RANGES.map((r) => (
        <button
          key={r}
          type="button"
          role="radio"
          aria-checked={r === range}
          title={rangeLabel(r)}
          onClick={() => setRange(r)}
          className={cn(
            "h-7 min-w-9 rounded-md px-2 text-[12px] font-medium text-muted-foreground tabular transition-[color,background-color,box-shadow] duration-150 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
            r === range && "bg-card text-foreground shadow-[var(--elev-1)] dark:bg-accent",
          )}
        >
          {r}
        </button>
      ))}
    </div>
  );
}
