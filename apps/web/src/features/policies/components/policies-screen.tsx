"use client";

import { MoreHorizontalIcon, PencilIcon, PlusIcon, ShieldCheckIcon, Trash2Icon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";
import { usePermissions } from "@/features/auth/api";
import { useScopeNamer } from "@/features/budgets/components/scope-picker";
import { errorMessage } from "@/lib/api/errors";
import type { Rule } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";
import { ACTION_LABEL, paramsSummary, ruleKindSpec } from "@/lib/policies";
import type { RuleAction } from "@/lib/api/types";

import { useDeletePolicy, usePolicies, useUpdatePolicy } from "../api";
import { PolicyDialog } from "./policy-dialog";
import { RuleIcon } from "./rule-icon";

const ACTION_TONE: Record<string, "warning" | "info" | "primary" | "neutral"> = {
  reject: "warning",
  throttle: "info",
  cap: "primary",
  alert: "neutral",
};

function RuleRow({ rule, canWrite, onEdit, onDelete }: { rule: Rule; canWrite: boolean; onEdit: () => void; onDelete: () => void }) {
  const update = useUpdatePolicy();
  const scopeName = useScopeNamer();
  const spec = ruleKindSpec(rule.kind);
  return (
    <li className={cn("flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:gap-4", !rule.enabled && "opacity-60")}>
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <RuleIcon kind={rule.kind} />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-[13.5px] font-semibold">{rule.name}</span>
            <span className="text-[12px] text-subtle">{spec?.label ?? rule.kind}</span>
          </div>
          <div className="mt-0.5 truncate text-[12.5px] text-muted-foreground">{paramsSummary(rule.kind, rule.params)}</div>
          <div className="mt-1 text-[11.5px] text-subtle">
            Applies to <span className="text-muted-foreground">{scopeName(rule.scope_type, rule.scope_id)}</span>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4 pl-12 sm:pl-0">
        <Chip tone={ACTION_TONE[rule.action] ?? "neutral"}>{ACTION_LABEL[rule.action as RuleAction] ?? rule.action}</Chip>
        <div className="w-20 text-right">
          <div className="text-[14px] font-semibold tabular">{formatNumber(rule.triggered_count)}</div>
          <div className="text-[11px] text-subtle">triggered</div>
        </div>
        {canWrite ? (
          <>
            <Switch
              checked={rule.enabled}
              aria-label={rule.enabled ? `Disable ${rule.name}` : `Enable ${rule.name}`}
              onCheckedChange={(enabled) =>
                update.mutate({ id: rule.id, body: { enabled } }, { onError: (e) => toast.error(errorMessage(e)) })
              }
            />
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="subtle" size="icon-xs" aria-label={`Actions for ${rule.name}`} />}>
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
          </>
        ) : (
          <Chip tone={rule.enabled ? "success" : "neutral"}>{rule.enabled ? "On" : "Off"}</Chip>
        )}
      </div>
    </li>
  );
}

export function PoliciesScreen() {
  const q = usePolicies();
  const del = useDeletePolicy();
  const { canWrite } = usePermissions();
  const [dialog, setDialog] = React.useState<{ open: boolean; rule: Rule | null }>({ open: false, rule: null });
  const [toDelete, setToDelete] = React.useState<Rule | null>(null);
  const enabled = q.data?.filter((r) => r.enabled).length ?? 0;

  const newButton = canWrite && (
    <Button onClick={() => setDialog({ open: true, rule: null })}>
      <PlusIcon />
      New rule
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Policies"
        description="Waste controls that run before any budget is reserved: oversized prompts, runaway output, restricted models, injection attempts, retry storms and agent loops."
        actions={newButton}
      />
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={6} cols={4} />
          </div>
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : !q.data?.length ? (
          <EmptyState
            icon={ShieldCheckIcon}
            title="No policy rules yet"
            description="Rules stop waste at the door: a retry storm, an agent stuck in a loop or a 100K-token prompt is blocked with a clear error before it costs anything."
            action={newButton || undefined}
          />
        ) : (
          <>
            <div className="flex items-center justify-between px-5 pt-4 pb-1 text-xs text-muted-foreground">
              <span>
                {q.data.length} rule{q.data.length === 1 ? "" : "s"}, {enabled} enabled
              </span>
              <span className="hidden sm:inline">Trigger counts since each rule was created</span>
            </div>
            <ul className="divide-y divide-hairline">
              {q.data.map((r) => (
                <RuleRow key={r.id} rule={r} canWrite={canWrite} onEdit={() => setDialog({ open: true, rule: r })} onDelete={() => setToDelete(r)} />
              ))}
            </ul>
          </>
        )}
      </Surface>
      <PolicyDialog open={dialog.open} rule={dialog.rule} onOpenChange={(open) => setDialog((d) => ({ ...d, open }))} />
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`Delete "${toDelete?.name ?? ""}"?`}
        description="Requests will no longer be checked against this rule. To pause it instead, turn it off with its switch."
        confirmLabel="Delete rule"
        pending={del.isPending}
        onConfirm={() =>
          toDelete &&
          del.mutate(toDelete.id, {
            onSuccess: () => {
              toast.success("Rule deleted.");
              setToDelete(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </>
  );
}
