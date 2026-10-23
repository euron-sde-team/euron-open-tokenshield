"use client";

import { ArrowRightIcon, BanIcon, BotIcon, CircleUserIcon, KeyRoundIcon, TriangleAlertIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { CopyButton } from "@/components/copy-button";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { CacheChip, StatusChip } from "@/components/status-chip";
import { Chip } from "@/components/ui/chip";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import type { UsageEventDetail } from "@/lib/api/types";
import { ruleLabel } from "@/lib/chips";
import { cn } from "@/lib/cn";
import { formatDateTime, formatLatency, formatNumber, formatUsd } from "@/lib/format";

import { useRequestDetail } from "../api";

function Section({ title, children, hint }: { title: string; children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h3 className="mb-2.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.06em] text-subtle uppercase">
        {title}
        {hint}
      </h3>
      {children}
    </section>
  );
}

function Fact({ label, value, mono = false }: { label: React.ReactNode; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 text-[13px]">
      <dt className="flex shrink-0 items-center gap-1.5 text-muted-foreground">{label}</dt>
      <dd className={cn("min-w-0 truncate text-right text-foreground", mono && "font-mono text-[12px]")}>{value ?? "n/a"}</dd>
    </div>
  );
}

function TokenBar({ d }: { d: UsageEventDetail }) {
  const fresh = Math.max(0, d.input_tokens - d.cached_input_tokens);
  const total = fresh + d.cached_input_tokens + d.output_tokens;
  const parts = [
    { label: "Input", value: fresh, color: "var(--chart-spend)" },
    { label: "Cached input", value: d.cached_input_tokens, color: "var(--chart-avoided)" },
    { label: "Output", value: d.output_tokens, color: "var(--chart-rejected)" },
  ];
  return (
    <div>
      <div className="grid grid-cols-3 gap-2">
        {parts.map((p) => (
          <div key={p.label} className="rounded-xl bg-muted/70 px-3 py-2.5">
            <div className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
              <span className="size-2 rounded-[3px]" style={{ background: p.color }} aria-hidden />
              {p.label}
            </div>
            <div className="mt-1 text-[17px] font-semibold tabular">{formatNumber(p.value)}</div>
          </div>
        ))}
      </div>
      {total > 0 && (
        <div className="mt-2.5 flex h-1.5 gap-0.5 overflow-hidden rounded-full" aria-hidden>
          {parts
            .filter((p) => p.value > 0)
            .map((p) => (
              <div key={p.label} style={{ flexGrow: p.value, background: p.color }} />
            ))}
        </div>
      )}
      {d.usage_source !== "provider" && (
        <p className="mt-2 text-xs text-muted-foreground">
          Token counts source: <span className="font-medium text-foreground">{d.usage_source}</span>
          {d.usage_source === "none" ? " (no upstream call was made)." : " (estimated, the provider reported none)."}
        </p>
      )}
    </div>
  );
}

function Detail({ d }: { d: UsageEventDetail }) {
  const rejected = d.status === "REJECTED";
  return (
    <>
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusChip status={d.status} />
        <CacheChip status={d.cache_status} />
        {d.stream && <Chip tone="neutral">Streamed</Chip>}
        {!d.priced && <Chip tone="warning">Unpriced</Chip>}
        <Chip tone="neutral">HTTP {d.http_status}</Chip>
        <Chip tone="neutral" className="capitalize">
          {d.source}
        </Chip>
      </div>

      {(rejected || d.status === "ERROR" || d.status === "UNCERTAIN") && (d.rule || d.reason) && (
        <div
          className={cn(
            "mt-4 flex gap-3 rounded-xl px-4 py-3",
            rejected ? "bg-warning-soft" : d.status === "ERROR" ? "bg-danger-soft" : "bg-primary-soft",
          )}
        >
          {rejected ? (
            <BanIcon className="mt-0.5 size-4 shrink-0 text-warning" />
          ) : (
            <TriangleAlertIcon className={cn("mt-0.5 size-4 shrink-0", d.status === "ERROR" ? "text-danger" : "text-primary")} />
          )}
          <div className="min-w-0 text-[13px]">
            {d.rule && <div className="font-semibold text-foreground">{ruleLabel(d.rule)}</div>}
            {d.reason && <p className="mt-0.5 leading-relaxed text-muted-foreground">{d.reason}</p>}
            {rejected && <p className="mt-1 text-xs text-muted-foreground">Blocked before the provider was called: zero upstream spend.</p>}
          </div>
        </div>
      )}

      <Section title="Cost" hint={<Hint term="estimated" />}>
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-xl bg-muted/70 px-3 py-2.5">
            <div className="text-[11.5px] text-muted-foreground">Actual</div>
            <div className="mt-1 text-[17px] font-semibold tabular">{formatUsd(d.actual_cost_usd)}</div>
          </div>
          <div className="rounded-xl bg-muted/70 px-3 py-2.5">
            <div className="text-[11.5px] text-muted-foreground">Estimated</div>
            <div className="mt-1 text-[17px] font-semibold text-muted-foreground tabular">{formatUsd(d.estimated_cost_usd)}</div>
          </div>
          <div className="rounded-xl bg-savings-soft px-3 py-2.5">
            <div className="text-[11.5px] text-savings">Avoided</div>
            <div className="mt-1 text-[17px] font-semibold text-savings tabular">{formatUsd(d.avoided_cost_usd)}</div>
          </div>
        </div>
        <dl className="mt-2">
          <Fact
            label={
              <>
                Price version <Hint term="priceVersion" />
              </>
            }
            value={d.price_version != null ? `v${d.price_version}` : d.priced ? "Not charged" : "Unpriced"}
          />
        </dl>
      </Section>

      <Section title="Tokens">
        <TokenBar d={d} />
        <dl className="mt-1">
          <Fact label="Estimated input before the call" value={formatNumber(d.estimated_input_tokens)} />
        </dl>
      </Section>

      <Section title="Request">
        <dl className="divide-y divide-hairline">
          <Fact label="Time" value={formatDateTime(d.created_at)} />
          <Fact label="Model" value={d.model_alias} mono />
          <Fact label="Provider" value={d.provider ? `${d.provider}${d.upstream_model ? ` (${d.upstream_model})` : ""}` : null} />
          <Fact label="Latency" value={formatLatency(d.latency_ms)} />
          <Fact label="Endpoint" value={d.endpoint} mono />
          <Fact
            label="Project"
            value={
              d.project_id ? (
                <Link href={`/projects/${d.project_id}`} className="hover:text-primary hover:underline">
                  {d.project_name ?? d.project_id}
                </Link>
              ) : null
            }
          />
          <Fact
            label={
              <>
                <KeyRoundIcon className="size-3.5" /> API key
              </>
            }
            value={d.api_key_name ?? (d.source === "playground" ? "Playground" : null)}
          />
          <Fact
            label={
              <>
                <CircleUserIcon className="size-3.5" /> End user
              </>
            }
            value={d.end_user}
            mono
          />
          <Fact
            label={
              <>
                <BotIcon className="size-3.5" /> Agent task
              </>
            }
            value={
              d.task_id ? (
                <Link href={`/requests?task_id=${encodeURIComponent(d.task_id)}`} className="hover:text-primary hover:underline">
                  {d.task_id}
                </Link>
              ) : null
            }
            mono
          />
        </dl>
        {d.prompt_excerpt && (
          <div className="mt-3 rounded-xl bg-muted/70 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-muted-foreground">
            <span className="mb-1 block text-[11px] font-semibold tracking-wide text-subtle uppercase">Prompt excerpt</span>
            {d.prompt_excerpt}
          </div>
        )}
      </Section>

      <Section title="Budget reservations" hint={<Hint term="reservation" />}>
        {d.reservations?.length ? (
          <div className="overflow-hidden rounded-xl bg-muted/50">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="text-left text-[11px] text-subtle uppercase">
                  <th className="px-3 py-2 font-semibold">Budget</th>
                  <th className="px-3 py-2 text-right font-semibold">Reserved</th>
                  <th className="px-3 py-2 text-right font-semibold">Actual</th>
                  <th className="px-3 py-2 text-right font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {d.reservations.map((r) => (
                  <tr key={`${r.budget_id}-${r.created_at}`} className="border-t border-hairline">
                    <td className="max-w-40 truncate px-3 py-2">{r.budget_name ?? r.budget_id}</td>
                    <td className="px-3 py-2 text-right tabular">{formatUsd(r.amount_usd)}</td>
                    <td className="px-3 py-2 text-right tabular">{r.actual_usd != null ? formatUsd(r.actual_usd) : "n/a"}</td>
                    <td className="px-3 py-2 text-right">
                      <Chip tone={r.status === "settled" ? "success" : r.status === "reserved" || r.status === "uncertain" ? "primary" : "neutral"} className="capitalize">
                        {r.status}
                      </Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="rounded-xl bg-muted/50 px-3.5 py-3 text-[12.5px] text-muted-foreground">
            {d.cache_status === "HIT"
              ? "Cache hits reserve nothing: no upstream call, no spend."
              : d.status === "REJECTED"
                ? "Rejected before any reservation was made."
                : "No budget applied to this request."}
          </p>
        )}
      </Section>

      {!!d.reconciliations?.length && (
        <Section title="Reconciliations">
          <ul className="space-y-1.5">
            {d.reconciliations.map((r) => (
              <li key={r.created_at} className="flex items-center justify-between gap-3 rounded-xl bg-muted/50 px-3.5 py-2.5 text-[12.5px]">
                <span className="text-muted-foreground">{r.reason}</span>
                <span className="flex items-center gap-2 tabular">
                  <span className={cn("font-semibold", r.delta_cost_usd > 0 ? "text-warning" : "text-savings")}>
                    {r.delta_cost_usd > 0 ? "+" : ""}
                    {formatUsd(r.delta_cost_usd)}
                  </span>
                  <span className="text-faint">{formatDateTime(r.created_at)}</span>
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

export function RequestDrawer({ requestId, onClose }: { requestId: string | null; onClose: () => void }) {
  const q = useRequestDetail(requestId);
  return (
    <Sheet open={!!requestId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Request detail</SheetTitle>
          <SheetDescription render={<div />} className="flex items-center gap-1.5">
            <span className="truncate font-mono text-[12px]">{requestId}</span>
            {requestId && <CopyButton value={requestId} iconOnly variant="subtle" label="Copy request id" />}
          </SheetDescription>
        </SheetHeader>
        <SheetBody>
          {q.isPending ? (
            <div className="space-y-3">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-40 w-full" />
            </div>
          ) : q.isError ? (
            <ErrorState error={q.error} onRetry={() => void q.refetch()} title="Could not load this request" compact />
          ) : (
            <>
              <Detail d={q.data} />
              {q.data.project_id && (
                <Link
                  href={`/projects/${q.data.project_id}`}
                  className="mt-6 inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline"
                >
                  Open project <ArrowRightIcon className="size-3.5" />
                </Link>
              )}
            </>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
