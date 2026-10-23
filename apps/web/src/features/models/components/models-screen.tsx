"use client";

import {
  CheckCircle2Icon,
  CpuIcon,
  HistoryIcon,
  LockIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlugIcon,
  PlusIcon,
  ServerIcon,
  TagIcon,
  XCircleIcon,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePermissions } from "@/features/auth/api";
import { errorMessage } from "@/lib/api/errors";
import type { Model, Provider, ProviderTest } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDuration, formatLatency, formatTokens } from "@/lib/format";

import { useModels, useProviders, useTestProvider, useUpdateModel, useUpdateProvider } from "../api";
import { ModelDialog } from "./model-dialog";
import { PriceHistorySheet, PublishPriceDialog, perMillion } from "./price-dialogs";
import { ProviderDialog } from "./provider-dialog";

function ModelsTable({ canWrite, onAdd }: { canWrite: boolean; onAdd: () => void }) {
  const q = useModels();
  const update = useUpdateModel();
  const [history, setHistory] = React.useState<Model | null>(null);
  const [publish, setPublish] = React.useState<Model | null>(null);

  const toggle = (m: Model, body: { restricted?: boolean; enabled?: boolean }, msg: string) =>
    update.mutate({ id: m.id, body }, { onSuccess: () => toast.success(msg), onError: (e) => toast.error(errorMessage(e)) });

  if (q.isPending) return <div className="pt-3"><TableSkeleton rows={6} cols={6} /></div>;
  if (q.isError && !q.data) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data?.length)
    return (
      <EmptyState
        icon={CpuIcon}
        title="No models yet"
        description="A model maps an alias your apps request (like chat-small) to a provider's model, with a versioned price."
        action={canWrite ? <Button size="sm" onClick={onAdd}><PlusIcon />Add a model</Button> : undefined}
      />
    );

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Model</TableHead>
            <TableHead className="hidden md:table-cell">Provider</TableHead>
            <TableHead className="text-right">Input / 1M</TableHead>
            <TableHead className="hidden text-right sm:table-cell">Cached / 1M</TableHead>
            <TableHead className="text-right">Output / 1M</TableHead>
            <TableHead className="hidden text-right lg:table-cell">Context</TableHead>
            <TableHead className="text-right"><span className="sr-only">Actions</span></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {q.data.map((m) => (
            <TableRow key={m.id} className={cn(!m.enabled && "opacity-55")}>
              <TableCell>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-[12.5px] font-medium">{m.alias}</span>
                  {m.restricted && (
                    <Chip tone="warning" title="Restricted">
                      <LockIcon />
                      Restricted
                    </Chip>
                  )}
                  {!m.price && <Chip tone="danger">Unpriced</Chip>}
                  {!m.enabled && <Chip tone="neutral">Disabled</Chip>}
                  {m.kind === "embedding" && <Chip tone="info">Embedding</Chip>}
                </div>
                <div className="mt-0.5 font-mono text-[11.5px] text-subtle">{m.upstream_model}</div>
              </TableCell>
              <TableCell className="hidden md:table-cell">
                <div>{m.provider_name}</div>
                <div className="text-[11.5px] text-subtle">{m.provider_kind === "anthropic" ? "Anthropic API" : "OpenAI-compatible"}</div>
              </TableCell>
              <TableCell className="text-right tabular">{m.price ? perMillion(m.price.input_per_m) : <span className="text-faint">n/a</span>}</TableCell>
              <TableCell className="hidden text-right text-muted-foreground tabular sm:table-cell">
                {m.price ? perMillion(m.price.cached_input_per_m) : <span className="text-faint">n/a</span>}
              </TableCell>
              <TableCell className="text-right tabular">{m.price ? perMillion(m.price.output_per_m) : <span className="text-faint">n/a</span>}</TableCell>
              <TableCell className="hidden text-right text-muted-foreground tabular lg:table-cell">{formatTokens(m.context_window)}</TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-1">
                  {m.price && <span className="hidden text-[11px] text-subtle xl:inline">v{m.price.version}</span>}
                  <DropdownMenu>
                    <DropdownMenuTrigger render={<Button variant="subtle" size="icon-xs" aria-label={`Actions for ${m.alias}`} />}>
                      <MoreHorizontalIcon />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="min-w-52">
                      <DropdownMenuItem onClick={() => setHistory(m)}>
                        <HistoryIcon />
                        Price history
                      </DropdownMenuItem>
                      {canWrite && (
                        <>
                          <DropdownMenuItem onClick={() => setPublish(m)}>
                            <TagIcon />
                            Publish new price
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => toggle(m, { restricted: !m.restricted }, m.restricted ? "Restriction lifted." : "Model restricted.")}>
                            <LockIcon />
                            {m.restricted ? "Lift restriction" : "Restrict"}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => toggle(m, { enabled: !m.enabled }, m.enabled ? "Model disabled." : "Model enabled.")}>
                            <PencilIcon />
                            {m.enabled ? "Disable" : "Enable"}
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="flex flex-wrap gap-x-5 gap-y-1 px-5 py-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5"><Chip tone="warning"><LockIcon />Restricted</Chip><Hint term="restricted" /></span>
        <span className="flex items-center gap-1.5"><Chip tone="danger">Unpriced</Chip><Hint term="unpriced" /></span>
      </div>
      <PriceHistorySheet model={history} onClose={() => setHistory(null)} />
      <PublishPriceDialog model={publish} onClose={() => setPublish(null)} />
    </>
  );
}

function ProviderCard({ provider, canWrite, onEdit }: { provider: Provider; canWrite: boolean; onEdit: () => void }) {
  const test = useTestProvider();
  const update = useUpdateProvider();
  const [result, setResult] = React.useState<ProviderTest | { ok: false; message: string; latency_ms?: number } | null>(null);

  function runTest() {
    setResult(null);
    test.mutate(provider.id, {
      onSuccess: (r) => setResult(r),
      onError: (e) => setResult({ ok: false, message: errorMessage(e) }),
    });
  }

  return (
    <article className={cn("surface flex flex-col gap-4 p-4", !provider.enabled && "opacity-60")}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
            <ServerIcon className="size-4" />
          </span>
          <div className="min-w-0">
            <h3 className="truncate text-[14px] font-semibold">{provider.name}</h3>
            <div className="truncate font-mono text-[11.5px] text-muted-foreground">{provider.base_url}</div>
          </div>
        </div>
        {canWrite && (
          <Button variant="subtle" size="icon-xs" aria-label={`Edit ${provider.name}`} onClick={onEdit}>
            <PencilIcon />
          </Button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Chip tone="primary">{provider.kind === "anthropic" ? "Anthropic API" : "OpenAI-compatible"}</Chip>
        <Chip tone={provider.has_key ? "success" : "neutral"}>{provider.has_key ? `Key ${provider.key_hint ?? "sealed"}` : "No key"}</Chip>
        <Chip tone="neutral">
          {provider.model_count ?? 0} model{provider.model_count === 1 ? "" : "s"}
        </Chip>
        {provider.timeout_s != null && <Chip tone="neutral">Timeout {formatDuration(provider.timeout_s)}</Chip>}
      </div>
      {result && (
        <div role="status" className={cn("flex items-start gap-2 rounded-xl px-3 py-2.5 text-[12.5px]", result.ok ? "bg-savings-soft" : "bg-danger-soft")}>
          {result.ok ? <CheckCircle2Icon className="mt-px size-4 shrink-0 text-savings" /> : <XCircleIcon className="mt-px size-4 shrink-0 text-danger" />}
          <div className="min-w-0">
            <span className={cn("font-semibold", result.ok ? "text-savings" : "text-danger")}>
              {result.ok ? "Connected" : "Connection failed"}
              {result.latency_ms != null && result.ok ? ` in ${formatLatency(result.latency_ms)}` : ""}
            </span>
            <p className="mt-0.5 break-words text-muted-foreground">{result.message}</p>
          </div>
        </div>
      )}
      <div className="-mx-4 -mb-4 mt-auto flex items-center justify-between gap-3 rounded-b-[14px] bg-muted/50 px-4 py-2.5">
        <Button variant="outline" size="sm" onClick={runTest} disabled={test.isPending}>
          <PlugIcon />
          {test.isPending ? "Testing..." : "Test connection"}
        </Button>
        {canWrite && (
          <label className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
            {provider.enabled ? "Enabled" : "Disabled"}
            <Switch
              checked={provider.enabled}
              onCheckedChange={(enabled) => update.mutate({ id: provider.id, body: { enabled } }, { onError: (e) => toast.error(errorMessage(e)) })}
            />
          </label>
        )}
      </div>
    </article>
  );
}

function ProvidersGrid({ canWrite, onAdd, onEdit }: { canWrite: boolean; onAdd: () => void; onEdit: (p: Provider) => void }) {
  const q = useProviders();
  if (q.isPending)
    return (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-44 rounded-[14px]" />
        ))}
      </div>
    );
  if (q.isError && !q.data) return <div className="surface"><ErrorState error={q.error} onRetry={() => void q.refetch()} /></div>;
  if (!q.data?.length)
    return (
      <div className="surface">
        <EmptyState
          icon={ServerIcon}
          title="No providers yet"
          description="A provider is an upstream API: OpenAI, Anthropic, or any OpenAI-compatible server such as Ollama or vLLM."
          action={canWrite ? <Button size="sm" onClick={onAdd}><PlusIcon />Add a provider</Button> : undefined}
        />
      </div>
    );
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {q.data.map((p) => (
        <ProviderCard key={p.id} provider={p} canWrite={canWrite} onEdit={() => onEdit(p)} />
      ))}
    </div>
  );
}

export function ModelsScreen() {
  const { canWrite } = usePermissions();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = params.get("tab") === "providers" ? "providers" : "models";
  const [modelOpen, setModelOpen] = React.useState(false);
  const [providerDialog, setProviderDialog] = React.useState<{ open: boolean; provider: Provider | null }>({ open: false, provider: null });

  return (
    <>
      <PageHeader
        title="Models"
        description="The catalog clients can request, each mapped to a provider with a versioned price. Unpriced models are flagged, never treated as free."
        actions={
          canWrite &&
          (tab === "models" ? (
            <Button onClick={() => setModelOpen(true)}>
              <PlusIcon />
              Add model
            </Button>
          ) : (
            <Button onClick={() => setProviderDialog({ open: true, provider: null })}>
              <PlusIcon />
              Add provider
            </Button>
          ))
        }
      />
      <Tabs value={tab} onValueChange={(v) => router.replace(v === "providers" ? `${pathname}?tab=providers` : pathname, { scroll: false })}>
        <TabsList>
          <TabsTrigger value="models">
            <CpuIcon />
            Models
          </TabsTrigger>
          <TabsTrigger value="providers">
            <ServerIcon />
            Providers
          </TabsTrigger>
        </TabsList>
        <TabsContent value="models">
          <Surface className="overflow-hidden">
            <ModelsTable canWrite={canWrite} onAdd={() => setModelOpen(true)} />
          </Surface>
        </TabsContent>
        <TabsContent value="providers">
          <ProvidersGrid canWrite={canWrite} onAdd={() => setProviderDialog({ open: true, provider: null })} onEdit={(p) => setProviderDialog({ open: true, provider: p })} />
        </TabsContent>
      </Tabs>
      <ModelDialog open={modelOpen} onOpenChange={setModelOpen} />
      <ProviderDialog open={providerDialog.open} provider={providerDialog.provider} onOpenChange={(open) => setProviderDialog((d) => ({ ...d, open }))} />
    </>
  );
}
