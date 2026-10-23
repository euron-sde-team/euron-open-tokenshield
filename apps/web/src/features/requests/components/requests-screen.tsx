"use client";

import { ActivityIcon, FilterXIcon, SearchIcon } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { CacheChip, StatusChip } from "@/components/status-chip";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SimpleSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useModels } from "@/features/models/api";
import { useProjects } from "@/features/projects/api";
import type { UsageEvent } from "@/lib/api/types";
import { CACHE_STATUSES, cacheChip, REQUEST_STATUSES, ruleLabel, statusChip } from "@/lib/chips";
import { cn } from "@/lib/cn";
import { formatLatency, formatRelative, formatTime, formatTokens, formatUsd } from "@/lib/format";
import { useUiPrefs } from "@/lib/store";

import { useRequestLog, type RequestFilters } from "../api";
import { RequestDrawer } from "./request-drawer";

const FILTER_KEYS = ["project_id", "model", "status", "cache_status", "q", "task_id"] as const;

function readFilters(params: URLSearchParams): RequestFilters {
  const f: RequestFilters = {};
  for (const k of FILTER_KEYS) {
    const v = params.get(k);
    if (v) f[k] = v;
  }
  return f;
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function RowCost({ e }: { e: UsageEvent }) {
  if (e.cache_status === "HIT" && e.avoided_cost_usd > 0) {
    return (
      <span className="text-savings" title="Spend avoided by the cache">
        {formatUsd(e.avoided_cost_usd)} saved
      </span>
    );
  }
  if (e.status === "REJECTED") return <span className="text-faint">$0.00</span>;
  return <span>{formatUsd(e.actual_cost_usd)}</span>;
}

export function RequestsScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const autoRefresh = useUiPrefs((s) => s.autoRefresh);
  const setAutoRefresh = useUiPrefs((s) => s.setAutoRefresh);

  const urlFilters = React.useMemo(() => readFilters(new URLSearchParams(params.toString())), [params]);
  const selected = params.get("id");
  const [search, setSearch] = React.useState(urlFilters.q ?? "");
  const debouncedSearch = useDebounced(search, 300);

  const setParams = React.useCallback(
    (patch: Record<string, string | undefined>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  React.useEffect(() => {
    if ((urlFilters.q ?? "") !== debouncedSearch) setParams({ q: debouncedSearch || undefined });
  }, [debouncedSearch, urlFilters.q, setParams]);

  const filters = urlFilters;
  const log = useRequestLog(filters, autoRefresh);
  const projects = useProjects();
  const models = useModels();
  const rows = React.useMemo(() => log.data?.pages.flatMap((p) => p.items) ?? [], [log.data]);
  const hasFilters = FILTER_KEYS.some((k) => !!filters[k]);

  const projectOptions = [{ value: "", label: "All projects" }, ...(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))];
  const modelOptions = [{ value: "", label: "All models" }, ...(models.data ?? []).map((m) => ({ value: m.alias, label: m.alias }))];
  const statusOptions = [{ value: "", label: "Any status" }, ...REQUEST_STATUSES.map((s) => ({ value: s, label: statusChip(s).label }))];
  const cacheOptions = [{ value: "", label: "Any cache" }, ...CACHE_STATUSES.map((s) => ({ value: s, label: cacheChip(s).label }))];

  return (
    <>
      <PageHeader
        title="Requests"
        description="Every call through the gateway, newest first: who sent it, what it cost and what TokenShield decided."
        actions={
          <label className="flex items-center gap-2 rounded-lg bg-card px-3 py-1.5 text-[13px] font-medium shadow-[var(--elev-1)]">
            <span className="relative flex size-2">
              {autoRefresh && <span className="absolute inline-flex size-full animate-ping rounded-full bg-savings opacity-50" />}
              <span className={cn("relative inline-flex size-2 rounded-full", autoRefresh ? "bg-savings" : "bg-faint")} />
            </span>
            Live
            <Switch checked={autoRefresh} onCheckedChange={setAutoRefresh} aria-label="Auto refresh every 5 seconds" />
          </label>
        }
      />

      <div className="mb-3 grid grid-cols-2 gap-2 md:flex md:flex-wrap md:items-center">
        <div className="relative col-span-2 md:w-64">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search request id"
            aria-label="Search by request id"
            className="pl-9"
          />
        </div>
        <SimpleSelect aria-label="Project" placeholder="All projects" className="md:w-44" value={filters.project_id ?? ""} onValueChange={(v) => setParams({ project_id: v || undefined })} options={projectOptions} />
        <SimpleSelect aria-label="Model" placeholder="All models" className="md:w-40" value={filters.model ?? ""} onValueChange={(v) => setParams({ model: v || undefined })} options={modelOptions} />
        <SimpleSelect aria-label="Status" placeholder="Any status" className="md:w-36" value={filters.status ?? ""} onValueChange={(v) => setParams({ status: v || undefined })} options={statusOptions} />
        <SimpleSelect aria-label="Cache status" placeholder="Any cache result" className="md:w-36" value={filters.cache_status ?? ""} onValueChange={(v) => setParams({ cache_status: v || undefined })} options={cacheOptions} />
        {filters.task_id && (
          <span className="col-span-2 inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary-soft px-3 text-[12.5px] text-primary md:col-span-1">
            Task <span className="font-mono">{filters.task_id}</span>
          </span>
        )}
        {hasFilters && (
          <Button
            variant="ghost"
            className="col-span-2 md:col-span-1"
            onClick={() => {
              setSearch("");
              router.replace(pathname, { scroll: false });
            }}
          >
            <FilterXIcon />
            Clear filters
          </Button>
        )}
      </div>

      <Surface className="overflow-hidden">
        {log.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={10} cols={7} />
          </div>
        ) : log.isError && !log.data ? (
          <ErrorState error={log.error} onRetry={() => void log.refetch()} />
        ) : !rows.length ? (
          hasFilters ? (
            <EmptyState
              icon={FilterXIcon}
              title="No requests match these filters"
              description="Try a different project, model or status, or clear the filters to see everything."
              action={
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setSearch("");
                    router.replace(pathname, { scroll: false });
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={ActivityIcon}
              title="No requests yet"
              description="This is the live log of every LLM call through TokenShield. Send one from the Playground or point an OpenAI client at the gateway."
              action={
                <Button size="sm" onClick={() => router.push("/playground")}>
                  Open the Playground
                </Button>
              }
            />
          )
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead className="hidden md:table-cell">Request</TableHead>
                  <TableHead className="hidden lg:table-cell">Project</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead className="hidden text-right sm:table-cell">Tokens</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                  <TableHead className="hidden text-right xl:table-cell">Latency</TableHead>
                  <TableHead>Outcome</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((e) => (
                  <TableRow
                    key={e.id}
                    tabIndex={0}
                    role="button"
                    aria-label={`Open request ${e.request_id}`}
                    data-state={selected === e.request_id ? "selected" : undefined}
                    className="cursor-pointer focus-visible:bg-muted focus-visible:outline-none"
                    onClick={() => setParams({ id: e.request_id })}
                    onKeyDown={(ev) => {
                      if (ev.key === "Enter" || ev.key === " ") {
                        ev.preventDefault();
                        setParams({ id: e.request_id });
                      }
                    }}
                  >
                    <TableCell className="whitespace-nowrap tabular">
                      <div className="text-foreground">{formatTime(e.created_at)}</div>
                      <div className="text-[11px] text-subtle">{formatRelative(e.created_at)}</div>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <div className="max-w-[170px] truncate font-mono text-[12px] text-muted-foreground">{e.request_id}</div>
                      {e.task_id && <div className="max-w-[170px] truncate text-[11px] text-subtle">task {e.task_id}</div>}
                    </TableCell>
                    <TableCell className="hidden max-w-[180px] lg:table-cell">
                      <div className="truncate">{e.project_name ?? "n/a"}</div>
                      <div className="truncate text-[11px] text-subtle">{e.api_key_name ?? (e.source === "playground" ? "Playground" : e.end_user ?? "")}</div>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-[140px] truncate font-mono text-[12px]">{e.model_alias ?? "n/a"}</div>
                      <div className="max-w-[140px] truncate text-[11px] text-subtle">{e.provider ?? ""}</div>
                    </TableCell>
                    <TableCell className="hidden text-right whitespace-nowrap tabular sm:table-cell">
                      {e.status === "REJECTED" ? (
                        <span className="text-faint">~{formatTokens(e.estimated_input_tokens)}</span>
                      ) : (
                        <>
                          <span>{formatTokens(e.input_tokens)}</span>
                          <span className="text-faint"> / </span>
                          <span>{formatTokens(e.output_tokens)}</span>
                        </>
                      )}
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap tabular">
                      <RowCost e={e} />
                    </TableCell>
                    <TableCell className="hidden text-right whitespace-nowrap text-muted-foreground tabular xl:table-cell">
                      {formatLatency(e.latency_ms)}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-1">
                        <StatusChip status={e.status} withHint={false} />
                        {e.cache_status !== "BYPASS" && <CacheChip status={e.cache_status} withHint={false} />}
                      </div>
                      {e.rule && <div className="mt-0.5 max-w-[160px] truncate text-[11px] text-subtle">{ruleLabel(e.rule)}</div>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex items-center justify-between gap-3 px-5 py-3 text-xs text-muted-foreground">
              <span className="tabular">
                Showing {rows.length.toLocaleString("en-US")} request{rows.length === 1 ? "" : "s"}
                {autoRefresh ? ", refreshing every 5 s" : ""}
              </span>
              {log.hasNextPage ? (
                <Button variant="outline" size="sm" onClick={() => void log.fetchNextPage()} disabled={log.isFetchingNextPage}>
                  {log.isFetchingNextPage ? "Loading..." : "Load older"}
                </Button>
              ) : (
                <span>End of the log</span>
              )}
            </div>
          </>
        )}
      </Surface>

      <RequestDrawer requestId={selected} onClose={() => setParams({ id: undefined })} />
    </>
  );
}
