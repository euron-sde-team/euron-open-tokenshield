"use client";

import { BellIcon, CheckCheckIcon, CheckIcon, CircleAlertIcon, OctagonAlertIcon, TriangleAlertIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import type { Alert } from "@/lib/api/types";
import { severityTone } from "@/lib/chips";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";

import { useAckAlert, useAckAllAlerts, useAlerts } from "../api";

export function AlertIcon({ alert, className }: { alert: Pick<Alert, "severity">; className?: string }) {
  const tone = severityTone(alert.severity);
  const Icon = tone === "danger" ? OctagonAlertIcon : tone === "warning" ? TriangleAlertIcon : CircleAlertIcon;
  return (
    <span
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-lg",
        tone === "danger" && "bg-danger-soft text-danger",
        tone === "warning" && "bg-warning-soft text-warning",
        (tone === "info" || tone === "neutral") && "bg-info-soft text-info",
        className,
      )}
    >
      <Icon className="size-3.5" />
    </span>
  );
}

export function AlertsBell() {
  const { data, isPending, isError, error } = useAlerts(false);
  const ack = useAckAlert();
  const ackAll = useAckAllAlerts();
  const { canWrite } = usePermissions();
  const count = data?.unacknowledged ?? 0;

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="subtle" size="icon" className="relative" aria-label={count ? `Alerts, ${count} unacknowledged` : "Alerts"} />
        }
      >
        <BellIcon />
        {count > 0 && (
          <span className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] leading-none font-bold text-white tabular ring-2 ring-background dark:text-[#1a0a0e]">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent className="w-[22rem]">
        <div className="flex items-center justify-between px-4 pt-3.5 pb-2">
          <div>
            <div className="text-[13px] font-semibold">Alerts</div>
            <div className="text-xs text-muted-foreground">Budget thresholds, blocked users and policy matches.</div>
          </div>
          {canWrite && count > 0 && (
            <Button variant="ghost" size="xs" onClick={() => ackAll.mutate()} disabled={ackAll.isPending}>
              <CheckCheckIcon />
              All read
            </Button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto px-2 pb-2">
          {isPending ? (
            <div className="space-y-2 p-2">
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </div>
          ) : isError ? (
            <p className="px-2 py-6 text-center text-xs text-muted-foreground">{errorMessage(error)}</p>
          ) : !data?.items.length ? (
            <div className="px-4 py-8 text-center">
              <div className="mx-auto mb-2 flex size-9 items-center justify-center rounded-xl bg-savings-soft text-savings">
                <CheckIcon className="size-4" />
              </div>
              <p className="text-[13px] font-medium">All clear</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Alerts appear here when a budget crosses its threshold or a policy set to alert matches.
              </p>
            </div>
          ) : (
            <ul className="space-y-0.5">
              {data.items.map((a) => (
                <li key={a.id} className="group flex gap-2.5 rounded-lg px-2 py-2 hover:bg-muted/60">
                  <AlertIcon alert={a} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[12.5px] leading-snug text-foreground">{a.message}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      <span className="capitalize">{a.kind}</span> · {formatRelative(a.created_at)}
                    </p>
                  </div>
                  {canWrite && (
                    <Button
                      variant="subtle"
                      size="icon-xs"
                      aria-label="Mark as read"
                      className="opacity-70 group-hover:opacity-100"
                      onClick={() => ack.mutate(a.id)}
                    >
                      <CheckIcon />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
