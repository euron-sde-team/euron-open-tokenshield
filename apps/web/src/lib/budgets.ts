import type { BudgetPeriod, BudgetScopeType } from "./api/types";

export const BUDGET_SCOPES: { value: BudgetScopeType; label: string; help: string }[] = [
  { value: "global", label: "Whole gateway", help: "Every request through TokenShield counts." },
  { value: "team", label: "Team", help: "All projects owned by one team." },
  { value: "project", label: "Project", help: "One application or service." },
  { value: "api_key", label: "API key", help: "A single key, for example a staging key." },
  { value: "model", label: "Model", help: "One model alias across every project." },
  { value: "end_user", label: "End user", help: "Per end user (x-tokenshield-user header). Use * for each user separately." },
];

export const BUDGET_PERIODS: { value: BudgetPeriod; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
  { value: "total", label: "Total" },
];

export function scopeTypeLabel(scope: string): string {
  return BUDGET_SCOPES.find((s) => s.value === scope)?.label ?? scope;
}

/** The scope type needs a concrete target (everything except the whole gateway). */
export function scopeNeedsId(scope: BudgetScopeType): boolean {
  return scope !== "global";
}

export interface BudgetFormValues {
  name: string;
  scopeType: BudgetScopeType;
  scopeId: string;
  period: BudgetPeriod;
  limit: string;
  mode: "hard" | "soft";
  threshold: string;
}

/** Validate the budget form; returns field errors keyed by field name. */
export function validateBudget(v: BudgetFormValues): Partial<Record<keyof BudgetFormValues, string>> {
  const errors: Partial<Record<keyof BudgetFormValues, string>> = {};
  if (!v.name.trim()) errors.name = "Give the budget a name people will recognise in alerts.";
  if (scopeNeedsId(v.scopeType) && !v.scopeId.trim()) errors.scopeId = "Pick what this budget applies to.";
  const limit = Number(v.limit);
  if (!v.limit.trim() || !Number.isFinite(limit) || limit <= 0) errors.limit = "Enter a limit above $0.";
  const t = Number(v.threshold);
  if (!Number.isInteger(t) || t < 1 || t > 100) errors.threshold = "Use a whole number from 1 to 100.";
  return errors;
}

/** Human description of a budget window: "Oct 1 to Nov 1". */
export function windowLabel(start: string | null | undefined, end: string | null | undefined): string {
  if (!start) return "Since creation";
  const fmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  const s = fmt.format(new Date(start));
  if (!end) return `Since ${s}`;
  return `${s} to ${fmt.format(new Date(end))}`;
}
