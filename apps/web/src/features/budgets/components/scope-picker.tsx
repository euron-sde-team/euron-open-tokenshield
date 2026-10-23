"use client";

import { Input } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { useKeys } from "@/features/keys/api";
import { useModels } from "@/features/models/api";
import { useProjects } from "@/features/projects/api";
import { useTeams } from "@/features/teams/api";
import type { BudgetScopeType } from "@/lib/api/types";
import { BUDGET_SCOPES, scopeNeedsId } from "@/lib/budgets";

/** Target picker that follows the scope type: team, project, key, model or end user. */
export function ScopePicker({
  scopeType,
  value,
  onChange,
  disabled,
  error,
}: {
  scopeType: BudgetScopeType;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  error?: string;
}) {
  const teams = useTeams();
  const projects = useProjects();
  const keys = useKeys();
  const models = useModels();

  if (!scopeNeedsId(scopeType)) return null;

  if (scopeType === "end_user") {
    return (
      <Field
        label="End user id"
        htmlFor="budget-scope"
        error={error}
        hint={
          <>
            The value of the <code className="font-mono">x-tokenshield-user</code> header. Use <code className="font-mono">*</code> to give
            each user their own allowance.
          </>
        }
      >
        <Input id="budget-scope" value={value} disabled={disabled} placeholder="* or student-0042" onChange={(e) => onChange(e.target.value)} />
      </Field>
    );
  }

  const options =
    scopeType === "team"
      ? (teams.data ?? []).map((t) => ({ value: t.id, label: t.name }))
      : scopeType === "project"
        ? (projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))
        : scopeType === "api_key"
          ? (keys.data ?? []).map((k) => ({ value: k.id, label: `${k.name} (${k.project_name ?? "project"})` }))
          : (models.data ?? []).map((m) => ({ value: m.alias, label: m.alias }));
  const label = BUDGET_SCOPES.find((s) => s.value === scopeType)?.label ?? "Target";
  return (
    <Field label={label} htmlFor="budget-scope" error={error}>
      <SimpleSelect
        id="budget-scope"
        value={value}
        onValueChange={onChange}
        options={options}
        disabled={disabled}
        placeholder={options.length ? `Choose a ${label.toLowerCase()}` : `No ${label.toLowerCase()}s yet`}
      />
    </Field>
  );
}

/** Resolve a scope (type + id) to a readable name from cached lists. */
export function useScopeNamer(): (scopeType: string, scopeId: string | null) => string {
  const teams = useTeams();
  const projects = useProjects();
  const keys = useKeys();
  return (scopeType, scopeId) => {
    if (scopeType === "global" || !scopeId) return "Whole gateway";
    if (scopeType === "team") return teams.data?.find((t) => t.id === scopeId)?.name ?? "Team";
    if (scopeType === "project") return projects.data?.find((p) => p.id === scopeId)?.name ?? "Project";
    if (scopeType === "api_key") return keys.data?.find((k) => k.id === scopeId)?.name ?? "API key";
    if (scopeType === "end_user") return scopeId === "*" ? "Each end user" : scopeId;
    return scopeId;
  };
}
