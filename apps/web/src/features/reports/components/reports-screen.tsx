"use client";

import { DownloadIcon, FileSpreadsheetIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Field } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePermissions } from "@/features/auth/api";
import { useProjects } from "@/features/projects/api";
import { errorMessage } from "@/lib/api/errors";
import type { ExportJob, RangeKey } from "@/lib/api/types";
import { formatBytes, formatDateTime, formatNumber } from "@/lib/format";
import { RANGES, rangeLabel } from "@/lib/range";

import { useCreateExport, useDownloadExport, useExports } from "../api";

function paramsLabel(job: ExportJob, projectName: (id: string) => string | undefined): string {
  const p = job.params as { range?: string; project_id?: string | null };
  const range = p.range ? rangeLabel(p.range as RangeKey) : "All time";
  return p.project_id ? `${range}, ${projectName(p.project_id) ?? "one project"}` : `${range}, all projects`;
}

export function ReportsScreen() {
  const q = useExports();
  const projects = useProjects();
  const create = useCreateExport();
  const download = useDownloadExport();
  const { canWrite } = usePermissions();
  const [range, setRange] = React.useState<RangeKey>("30d");
  const [projectId, setProjectId] = React.useState("");
  const projectName = (id: string) => projects.data?.find((p) => p.id === id)?.name;

  function run() {
    create.mutate(
      { range, project_id: projectId || null },
      {
        onSuccess: (job) => toast.success(`Export ready: ${formatNumber(job.rows)} rows.`),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  function fetchFile(job: ExportJob) {
    download.mutate(job.id, {
      onSuccess: (d) => {
        if (!d.url) {
          toast.error("The file is not available yet. Retry in a moment.");
          return;
        }
        const a = document.createElement("a");
        a.href = d.url;
        a.download = d.filename;
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
      },
      onError: (e) => toast.error(errorMessage(e)),
    });
  }

  return (
    <>
      <PageHeader
        title="Reports"
        description="CSV exports of the request log for finance and chargeback: one row per request with attribution, tokens, cost, cache and status."
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Surface className="h-fit">
          <SurfaceHeader title="New export" description="Written to object storage, downloaded through a short-lived link." />
          <div className="space-y-4 px-5 pb-5">
            <Field label="Time range" htmlFor="exp-range">
              <SimpleSelect id="exp-range" value={range} onValueChange={(v) => setRange((v || "30d") as RangeKey)} options={RANGES.map((r) => ({ value: r, label: rangeLabel(r) }))} />
            </Field>
            <Field label="Project" htmlFor="exp-project">
              <SimpleSelect
                id="exp-project"
                value={projectId}
                onValueChange={setProjectId}
                options={[{ value: "", label: "All projects" }, ...(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))]}
              />
            </Field>
            {canWrite ? (
              <Button className="w-full" onClick={run} disabled={create.isPending}>
                <FileSpreadsheetIcon />
                {create.isPending ? "Exporting..." : "Create CSV export"}
              </Button>
            ) : (
              <p className="rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">Viewers can download existing exports. Ask an admin to create one.</p>
            )}
          </div>
        </Surface>
        <Surface className="overflow-hidden lg:col-span-2">
          <SurfaceHeader title="Exports" description="Newest first" />
          {q.isPending ? (
            <TableSkeleton rows={4} cols={4} />
          ) : q.isError && !q.data ? (
            <ErrorState error={q.error} onRetry={() => void q.refetch()} />
          ) : !q.data?.length ? (
            <EmptyState
              icon={FileSpreadsheetIcon}
              title="No exports yet"
              description="Pick a range and project, then create an export. It appears here ready to download, and stays available for later."
              action={
                canWrite ? (
                  <Button size="sm" onClick={run} disabled={create.isPending}>
                    Export the last 30 days
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Export</TableHead>
                  <TableHead className="text-right">Rows</TableHead>
                  <TableHead className="hidden text-right sm:table-cell">Size</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right"><span className="sr-only">Download</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {q.data.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell>
                      <div className="font-medium">{paramsLabel(job, projectName)}</div>
                      <div className="text-[11.5px] text-subtle">{formatDateTime(job.created_at)}</div>
                    </TableCell>
                    <TableCell className="text-right tabular">{formatNumber(job.rows)}</TableCell>
                    <TableCell className="hidden text-right text-muted-foreground tabular sm:table-cell">{formatBytes(job.bytes)}</TableCell>
                    <TableCell>
                      <Chip tone={job.status === "ready" ? "success" : job.status === "failed" ? "danger" : "info"} dot className="capitalize">
                        {job.status}
                      </Chip>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="xs" disabled={job.status !== "ready" || download.isPending} onClick={() => fetchFile(job)}>
                        <DownloadIcon />
                        CSV
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Surface>
      </div>
    </>
  );
}
