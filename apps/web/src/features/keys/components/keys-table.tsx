"use client";

import { KeyRoundIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api/errors";
import type { ApiKey } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatRelative, formatTokens } from "@/lib/format";

import { useKeys, useRevokeKey } from "../api";

export function keyStatus(k: Pick<ApiKey, "revoked_at" | "expires_at">, now = new Date()): "active" | "revoked" | "expired" {
  if (k.revoked_at) return "revoked";
  if (k.expires_at && new Date(k.expires_at) <= now) return "expired";
  return "active";
}

function Limits({ k }: { k: ApiKey }) {
  const parts = [
    k.rpm_limit ? `${formatTokens(k.rpm_limit)} rpm` : null,
    k.tpm_limit ? `${formatTokens(k.tpm_limit)} tpm` : null,
    k.concurrency_limit ? `${k.concurrency_limit} conc.` : null,
  ].filter(Boolean);
  return parts.length ? <span className="tabular">{parts.join(" · ")}</span> : <span className="text-faint">No limits</span>;
}

export function KeysTable({
  projectId,
  includeRevoked,
  canWrite,
  onCreate,
  showProject = true,
}: {
  projectId?: string;
  includeRevoked: boolean;
  canWrite: boolean;
  onCreate: () => void;
  showProject?: boolean;
}) {
  const q = useKeys(projectId, includeRevoked);
  const revoke = useRevokeKey();
  const [target, setTarget] = React.useState<ApiKey | null>(null);

  if (q.isPending) return <div className="pt-3"><TableSkeleton rows={5} cols={5} /></div>;
  if (q.isError && !q.data) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data?.length)
    return (
      <EmptyState
        icon={KeyRoundIcon}
        title={projectId ? "This project has no keys" : "No API keys yet"}
        description="Apps call the gateway with a TokenShield key instead of a provider key. Each key bills to one project and can carry its own rate limits."
        action={
          canWrite ? (
            <Button size="sm" onClick={onCreate}>
              <PlusIcon />
              Create a key
            </Button>
          ) : undefined
        }
      />
    );

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Key</TableHead>
            {showProject && <TableHead className="hidden md:table-cell">Project</TableHead>}
            <TableHead className="hidden lg:table-cell">Limits</TableHead>
            <TableHead className="hidden sm:table-cell">Last used</TableHead>
            <TableHead>Status</TableHead>
            {canWrite && <TableHead className="text-right"><span className="sr-only">Actions</span></TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {q.data.map((k) => {
            const status = keyStatus(k);
            return (
              <TableRow key={k.id} className={cn(status !== "active" && "opacity-60")}>
                <TableCell>
                  <div className="font-medium">{k.name}</div>
                  <div className="font-mono text-[11.5px] text-muted-foreground">{k.display}</div>
                </TableCell>
                {showProject && (
                  <TableCell className="hidden md:table-cell">
                    <Link href={`/projects/${k.project_id}`} className="hover:text-primary hover:underline">
                      {k.project_name ?? "Project"}
                    </Link>
                  </TableCell>
                )}
                <TableCell className="hidden text-muted-foreground lg:table-cell">
                  <Limits k={k} />
                </TableCell>
                <TableCell className="hidden text-muted-foreground sm:table-cell">{formatRelative(k.last_used_at)}</TableCell>
                <TableCell>
                  <Chip tone={status === "active" ? "success" : status === "revoked" ? "danger" : "neutral"} dot>
                    {status === "active" ? "Active" : status === "revoked" ? "Revoked" : "Expired"}
                  </Chip>
                </TableCell>
                {canWrite && (
                  <TableCell className="text-right">
                    {status === "active" && (
                      <Button variant="destructive-soft" size="xs" onClick={() => setTarget(k)}>
                        Revoke
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <ConfirmDialog
        open={!!target}
        onOpenChange={(o) => !o && setTarget(null)}
        title={`Revoke "${target?.name ?? ""}"?`}
        description={
          <>
            Requests using <span className="font-mono">{target?.display}</span> start failing with 401 immediately. This cannot be undone; create a
            new key to restore access.
          </>
        }
        confirmLabel="Revoke key"
        pending={revoke.isPending}
        onConfirm={() =>
          target &&
          revoke.mutate(target.id, {
            onSuccess: () => {
              toast.success("Key revoked.");
              setTarget(null);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </>
  );
}
