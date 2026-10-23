"use client";

import * as React from "react";
import { toast } from "sonner";

import { Hint } from "@/components/hint";
import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { errorMessage } from "@/lib/api/errors";
import type { Budget, BudgetPeriod, BudgetScopeType } from "@/lib/api/types";
import { BUDGET_PERIODS, BUDGET_SCOPES, scopeNeedsId, validateBudget, type BudgetFormValues } from "@/lib/budgets";

import { useCreateBudget, useUpdateBudget } from "../api";
import { ScopePicker } from "./scope-picker";

function initial(b?: Budget | null): BudgetFormValues {
  return {
    name: b?.name ?? "",
    scopeType: (b?.scope_type as BudgetScopeType) ?? "project",
    scopeId: b?.scope_id ?? "",
    period: (b?.period as BudgetPeriod) ?? "monthly",
    limit: b ? String(b.limit_usd) : "",
    mode: (b?.mode as "hard" | "soft") ?? "hard",
    threshold: String(b?.alert_threshold_pct ?? 80),
  };
}

export function BudgetDialog({ open, onOpenChange, budget }: { open: boolean; onOpenChange: (o: boolean) => void; budget?: Budget | null }) {
  const editing = !!budget;
  const [v, setV] = React.useState<BudgetFormValues>(() => initial(budget));
  const [errors, setErrors] = React.useState<ReturnType<typeof validateBudget>>({});
  const [serverError, setServerError] = React.useState<string | null>(null);
  const create = useCreateBudget();
  const update = useUpdateBudget();
  const pending = create.isPending || update.isPending;

  React.useEffect(() => {
    if (open) {
      setV(initial(budget));
      setErrors({});
      setServerError(null);
    }
  }, [open, budget]);

  const set = <K extends keyof BudgetFormValues>(k: K, value: BudgetFormValues[K]) => setV((s) => ({ ...s, [k]: value }));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validateBudget(v);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setServerError(null);
    const done = {
      onSuccess: () => {
        toast.success(editing ? "Budget updated." : "Budget created. It applies to the next request.");
        onOpenChange(false);
      },
      onError: (err: unknown) => setServerError(errorMessage(err)),
    };
    if (editing && budget) {
      update.mutate(
        {
          id: budget.id,
          body: { name: v.name.trim(), limit_usd: Number(v.limit), mode: v.mode, alert_threshold_pct: Number(v.threshold) },
        },
        done,
      );
    } else {
      create.mutate(
        {
          name: v.name.trim(),
          scope_type: v.scopeType,
          scope_id: scopeNeedsId(v.scopeType) ? v.scopeId.trim() : null,
          period: v.period,
          limit_usd: Number(v.limit),
          mode: v.mode,
          alert_threshold_pct: Number(v.threshold),
          enabled: true,
        },
        done,
      );
    }
  }

  const scopeHelp = BUDGET_SCOPES.find((s) => s.value === v.scopeType)?.help;

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit budget" : "New budget"}</DialogTitle>
          <DialogDescription>
            {editing
              ? "Scope and period are fixed once created. Change the limit, mode or alert threshold here."
              : "Cap spend for a scope over a period. Hard budgets block before the provider is called."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <Field label="Name" htmlFor="budget-name" error={errors.name}>
              <Input id="budget-name" value={v.name} onChange={(e) => set("name", e.target.value)} placeholder="Support Copilot monthly" />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Applies to" htmlFor="budget-scope-type" hint={editing ? undefined : scopeHelp}>
                <SimpleSelect
                  id="budget-scope-type"
                  value={v.scopeType}
                  disabled={editing}
                  onValueChange={(s) => setV((st) => ({ ...st, scopeType: (s || "global") as BudgetScopeType, scopeId: s === "end_user" ? "*" : "" }))}
                  options={BUDGET_SCOPES.map((s) => ({ value: s.value, label: s.label }))}
                />
              </Field>
              <Field label="Period" htmlFor="budget-period" hint={editing ? undefined : "Windows reset at 00:00 UTC."}>
                <SimpleSelect
                  id="budget-period"
                  value={v.period}
                  disabled={editing}
                  onValueChange={(p) => set("period", (p || "monthly") as BudgetPeriod)}
                  options={BUDGET_PERIODS}
                />
              </Field>
            </div>
            <ScopePicker scopeType={v.scopeType} value={v.scopeId} onChange={(id) => set("scopeId", id)} disabled={editing} error={errors.scopeId} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Limit (USD)" htmlFor="budget-limit" error={errors.limit}>
                <div className="relative">
                  <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[13px] text-faint">$</span>
                  <Input
                    id="budget-limit"
                    inputMode="decimal"
                    className="pl-6 tabular"
                    value={v.limit}
                    onChange={(e) => set("limit", e.target.value)}
                    placeholder="50.00"
                  />
                </div>
              </Field>
              <Field label="Alert at (%)" htmlFor="budget-threshold" error={errors.threshold} labelExtra={<Hint term="alertThreshold" />}>
                <Input
                  id="budget-threshold"
                  inputMode="numeric"
                  className="tabular"
                  value={v.threshold}
                  onChange={(e) => set("threshold", e.target.value)}
                />
              </Field>
            </div>
            <Field
              label="Mode"
              labelExtra={<Hint text="Hard blocks requests that would overspend, before any upstream call. Soft only alerts." />}
              hint={
                v.mode === "hard"
                  ? "Blocks a request when its worst-case cost would exceed what is left."
                  : "Never blocks. Raises an alert at the threshold so someone can act."
              }
            >
              <Segmented
                ariaLabel="Budget mode"
                value={v.mode}
                onChange={(m) => set("mode", m)}
                options={[
                  { value: "hard", label: "Hard (block)" },
                  { value: "soft", label: "Soft (alert only)" },
                ]}
              />
            </Field>
            {serverError && <FieldError>{serverError}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={pending}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Saving..." : editing ? "Save changes" : "Create budget"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
