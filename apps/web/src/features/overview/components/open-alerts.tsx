"use client";

import { BellRingIcon, CheckIcon } from "lucide-react";

import { ErrorState } from "@/components/error-state";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAckAlert, useAlerts } from "@/features/alerts/api";
import { AlertIcon } from "@/features/alerts/components/alerts-bell";
import { usePermissions } from "@/features/auth/api";
import { formatRelative } from "@/lib/format";

export function OpenAlerts() {
  const q = useAlerts(false);
  const ack = useAckAlert();
  const { canWrite } = usePermissions();
  const items = q.data?.items.slice(0, 4) ?? [];
  return (
    <Surface className="flex h-full flex-col">
      <SurfaceHeader
        title="Open alerts"
        description={q.data ? `${q.data.unacknowledged} unacknowledged` : "Budget and policy signals"}
      />
      <div className="flex-1 px-3 pb-3">
        {q.isPending ? (
          <div className="space-y-2 px-2 pb-2">
            <Skeleton className="h-11" />
            <Skeleton className="h-11" />
            <Skeleton className="h-11" />
          </div>
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} compact />
        ) : !items.length ? (
          <div className="flex flex-col items-center px-4 py-8 text-center">
            <div className="mb-2.5 flex size-10 items-center justify-center rounded-xl bg-savings-soft text-savings">
              <BellRingIcon className="size-4.5" />
            </div>
            <p className="text-[13px] font-semibold">No open alerts</p>
            <p className="mt-1 max-w-xs text-xs leading-relaxed text-muted-foreground">
              Budgets crossing their alert threshold and policies set to alert show up here.
            </p>
          </div>
        ) : (
          <ul className="space-y-0.5">
            {items.map((a) => (
              <li key={a.id} className="group flex items-start gap-2.5 rounded-lg px-2 py-2 hover:bg-muted/60">
                <AlertIcon alert={a} />
                <div className="min-w-0 flex-1">
                  <p className="text-[12.5px] leading-snug">{a.message}</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    <span className="capitalize">{a.kind}</span> · {formatRelative(a.created_at)}
                  </p>
                </div>
                {canWrite && (
                  <Button variant="subtle" size="icon-xs" aria-label="Mark as read" onClick={() => ack.mutate(a.id)}>
                    <CheckIcon />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Surface>
  );
}
