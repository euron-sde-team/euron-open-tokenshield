"use client";

import { CalendarRangeIcon, MoreHorizontalIcon, PencilIcon, PlusIcon, Trash2Icon, WalletIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import type { Budget } from "@/lib/api/types";
import { scopeTypeLabel, windowLabel } from "@/lib/budgets";
import { budgetRisk } from "@/lib/chips";
import { cn } from "@/lib/cn";
import { formatUsd } from "@/lib/format";

import { useBudgets, useDeleteBudget, useUpdateBudget } from "../api";
import { BudgetDialog } from "./budget-dialog";
import { BudgetMeter } from "./budget-meter";

function SummaryStat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "warning" | "danger" }) {
  return (
    <div className="rounded-xl bg-card px-4 py-3 shadow-[var(--elev-1)]">
      <div className="text-[12px] text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 text-[20px] font-semibold tabular", tone === "warning" && "text-warning", tone === "danger" && "text-danger")}>
        {value}
      </div>
    </div>
  );
}

function BudgetCard({
  budget,
  canWrite,
  onEdit,
  onDelete,
}: {
  budget: Budget;
  canWrite: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const update = useUpdateBudget();
  const remaining = Math.max(0, budget.limit_usd - (budget.spent_usd ?? 0));
  const risk = budgetRisk(budget.used_pct, budget.alert_threshold_pct);
  return (
    <article className={cn("surface flex flex-col gap-4 p-4 transition-opacity", !budget.enabled && "opacity-60")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-[14px] font-semibold">{budget.name}</h3>
          </div>
          <div className="mt-0.5 truncate text-[12.5px] text-muted-foreground">
            {scopeTypeLabel(budget.scope_type)}
            {budget.scope_type !== "global" && (
              <>
                {": "}
                <span className={cn("text-foreground", budget.scope_type === "end_user" || budget.scope_type === "model" ? "font-mono text-[12px]" : "")}>
                  {budget.scope_type === "end_user" && budget.scope_id === "*" ? "each user (*)" : (budget.scope_label ?? budget.scope_id)}
                </span>
              </>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Chip tone={budget.mode === "hard" ? "primary" : "neutral"}>{budget.mode === "hard" ? "Hard" : "Soft"}</Chip>
          {canWrite && (
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="subtle" size="icon-xs" aria-label={`Actions for ${budget.name}`} />}>
                <MoreHorizontalIcon />
              </DropdownMenuTrigger>
              <DropdownMenuContent className="min-w-40">
                <DropdownMenuItem onClick={onEdit}>
                  <PencilIcon />
                  Edit
                </DropdownMenuItem>
                <DropdownMenuItem variant="destructive" onClick={onDelete}>
                  <Trash2Icon />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      <BudgetMeter budget={budget} size="lg" />

      <div className="flex items-center justify-between gap-3 text-[12px] text-muted-foreground">
        <span className="flex min-w-0 items-center gap-1.5">
          <CalendarRangeIcon className="size-3.5 shrink-0" />
          <span className="truncate">
            <span className="capitalize">{budget.period}</span> · {windowLabel(budget.window_start, budget.window_end)}
          </span>
        </span>
        <span className={cn("shrink-0 tabular", risk === "over" && "font-semibold text-danger")}>
          {risk === "over" ? "Limit reached" : `${formatUsd(remaining)} left`}
        </span>
      </div>

      {canWrite && (
        <div className="-mx-4 -mb-4 flex items-center justify-between rounded-b-[14px] bg-muted/50 px-4 py-2.5 text-[12.5px]">
          <span className="text-muted-foreground">{budget.enabled ? "Enforced" : "Paused, not enforced"}</span>
          <Switch
            checked={budget.enabled}
            aria-label={budget.enabled ? `Pause ${budget.name}` : `Enable ${budget.name}`}
            onCheckedChange={(enabled) =>
              update.mutate(
                { id: budget.id, body: { enabled } },
                { onError: (e) => toast.error(errorMessage(e)), onSuccess: () => toast.success(enabled ? "Budget enabled." : "Budget paused.") },
              )
            }
          />
        </div>
      )}
    </article>
  );
}

export function BudgetsScreen() {
  const q = useBudgets();
  const del = useDeleteBudget();
  const { canWrite } = usePermissions();
  const [dialog, setDialog] = React.useState<{ open: boolean; budget: Budget | null }>({ open: false, budget: null });
  const [toDelete, setToDelete] = React.useState<Budget | null>(null);

  const list = React.useMemo(() => [...(q.data ?? [])].sort((a, b) => (b.used_pct ?? 0) - (a.used_pct ?? 0)), [q.data]);
  const atRisk = list.filter((b) => b.enabled && budgetRisk(b.used_pct, b.alert_threshold_pct) !== "ok").length;
  const hard = list.filter((b) => b.mode === "hard" && b.enabled).length;
  const limitTotal = list.filter((b) => b.scope_type === "global" && b.enabled)[0];

  const newButton = canWrite && (
    <Button onClick={() => setDialog({ open: true, budget: null })}>
      <PlusIcon />
      New budget
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Budgets"
        description={
          <>
            Spending limits per scope and period. Every request reserves its worst-case cost against all matching budgets at once{" "}
            <Hint term="reservation" className="inline-flex align-text-bottom" />
          </>
        }
        actions={newButton}
      />

      {q.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-[14px]" />
          ))}
        </div>
      ) : q.isError && !q.data ? (
        <div className="surface">
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        </div>
      ) : !list.length ? (
        <div className="surface">
          <EmptyState
            icon={WalletIcon}
            title="No budgets yet"
            description="Budgets are the shield. A hard budget rejects any request whose worst-case cost would exceed what is left, before the provider sees it."
            action={newButton || undefined}
          />
        </div>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <SummaryStat label="Budgets" value={list.length} />
            <SummaryStat
              label="Hard, enforcing"
              value={
                <span className="flex items-center gap-1.5">
                  {hard}
                  <Hint term="hardBudget" />
                </span>
              }
            />
            <SummaryStat label="At or over threshold" value={atRisk} tone={atRisk ? "warning" : undefined} />
            <SummaryStat
              label="Gateway cap"
              value={limitTotal ? `${formatUsd(limitTotal.spent_usd ?? 0)} / ${formatUsd(limitTotal.limit_usd)}` : "None"}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {list.map((b) => (
              <BudgetCard
                key={b.id}
                budget={b}
                canWrite={canWrite}
                onEdit={() => setDialog({ open: true, budget: b })}
                onDelete={() => setToDelete(b)}
              />
            ))}
          </div>
        </>
      )}

      <BudgetDialog open={dialog.open} budget={dialog.budget} onOpenChange={(open) => setDialog((d) => ({ ...d, open }))} />
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`Delete "${toDelete?.name ?? ""}"?`}
        description="Requests in this scope will no longer be checked against this limit. Spend history stays in the request log."
        confirmLabel="Delete budget"
        pending={del.isPending}
        onConfirm={() =>
          toDelete &&
          del.mutate(toDelete.id, {
            onSuccess: () => {
              toast.success("Budget deleted.");
              setToDelete(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </>
  );
}
