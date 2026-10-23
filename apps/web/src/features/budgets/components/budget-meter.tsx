import { Progress } from "@/components/ui/progress";
import type { Budget } from "@/lib/api/types";
import { budgetRisk } from "@/lib/chips";
import { cn } from "@/lib/cn";
import { formatPercent, formatUsd } from "@/lib/format";

export function riskTone(b: Pick<Budget, "used_pct" | "alert_threshold_pct">): "primary" | "warning" | "danger" {
  const r = budgetRisk(b.used_pct, b.alert_threshold_pct);
  return r === "over" ? "danger" : r === "warn" ? "warning" : "primary";
}

/** Spent of limit with a risk-colored bar and the threshold marked. */
export function BudgetMeter({ budget, size = "default" }: { budget: Budget; size?: "default" | "lg" }) {
  const used = budget.used_pct ?? 0;
  const tone = riskTone(budget);
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3 text-[12.5px] tabular">
        <span className="text-muted-foreground">
          <span className={cn("font-semibold text-foreground", size === "lg" && "text-[15px]")}>{formatUsd(budget.spent_usd ?? 0)}</span> of{" "}
          {formatUsd(budget.limit_usd)}
        </span>
        <span className={cn("font-semibold", tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : "text-muted-foreground")}>
          {formatPercent(used)}
        </span>
      </div>
      <div className="relative">
        <Progress value={used} tone={tone} className={size === "lg" ? "h-2" : undefined} label={`${budget.name}: ${formatPercent(used)} used`} />
        <span
          aria-hidden
          title={`Alert at ${budget.alert_threshold_pct}%`}
          className="absolute -top-0.5 h-[calc(100%+4px)] w-0.5 rounded-full bg-foreground/25"
          style={{ left: `${Math.min(100, budget.alert_threshold_pct)}%` }}
        />
      </div>
    </div>
  );
}
