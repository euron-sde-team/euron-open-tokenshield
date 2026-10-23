"use client";

import { WalletIcon } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { buttonVariants } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { useBudgets } from "@/features/budgets/api";
import { BudgetMeter } from "@/features/budgets/components/budget-meter";

export function BudgetHealth({ limit = 5 }: { limit?: number }) {
  const q = useBudgets();
  const top = (q.data ?? [])
    .filter((b) => b.enabled)
    .sort((a, b) => (b.used_pct ?? 0) - (a.used_pct ?? 0))
    .slice(0, limit);
  return (
    <Surface className="flex h-full flex-col">
      <SurfaceHeader
        title="Budget health"
        description="Closest to their limit first"
        action={
          <Link href="/budgets" className={buttonVariants({ variant: "ghost", size: "xs" })}>
            All budgets
          </Link>
        }
      />
      <div className="flex-1 px-5 pb-5">
        {q.isPending ? (
          <div className="space-y-5">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-3.5 w-1/2" />
                <Skeleton className="h-1.5 w-full" />
              </div>
            ))}
          </div>
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} compact />
        ) : !top.length ? (
          <EmptyState
            compact
            icon={WalletIcon}
            title="No budgets yet"
            description="A hard budget blocks requests before they overspend. Set one for the whole gateway or a single project."
            action={
              <Link href="/budgets" className={buttonVariants({ size: "sm" })}>
                Create a budget
              </Link>
            }
          />
        ) : (
          <ul className="space-y-4">
            {top.map((b) => (
              <li key={b.id}>
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="truncate text-[13px] font-medium">{b.name}</span>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <span className="text-[11px] text-subtle capitalize">{b.period}</span>
                    <Chip tone={b.mode === "hard" ? "primary" : "neutral"}>{b.mode === "hard" ? "Hard" : "Soft"}</Chip>
                  </div>
                </div>
                <BudgetMeter budget={b} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </Surface>
  );
}
