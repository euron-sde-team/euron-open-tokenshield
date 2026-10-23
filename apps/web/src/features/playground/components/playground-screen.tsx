"use client";

import { ArrowUpRightIcon, BanIcon, FlaskConicalIcon, LoaderIcon, PlayIcon, SparklesIcon, TriangleAlertIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { CacheChip } from "@/components/status-chip";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button, buttonVariants } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { usePermissions } from "@/features/auth/api";
import { useModels } from "@/features/models/api";
import { useProjects } from "@/features/projects/api";
import { ApiError, errorMessage, validationMessages } from "@/lib/api/errors";
import type { PlaygroundRequest } from "@/lib/api/types";
import { ruleLabel } from "@/lib/chips";
import { cn } from "@/lib/cn";
import { formatLatency, formatNumber, formatUsd } from "@/lib/format";

import { PlaygroundError, usePlaygroundRun, type GatewayHeaders, type PlaygroundResult } from "../api";

const ERROR_TITLES: Record<string, string> = {
  budget_exceeded: "Blocked by a hard budget",
  rate_limited: "Rate limited",
  rpm_limit: "Requests per minute limit reached",
  tpm_limit: "Tokens per minute limit reached",
  concurrency_limit: "Concurrency limit reached",
  policy_violation: "Blocked by a policy",
  model_unpriced: "Model has no price",
  model_restricted: "Restricted model",
  upstream_error: "The provider returned an error",
  upstream_timeout: "The provider timed out",
  dependency_unavailable: "Budget store unavailable, failing closed",
};

function HeaderChips({ h, elapsedMs }: { h: GatewayHeaders; elapsedMs?: number }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {h.cache && <CacheChip status={h.cache} />}
      {h.costUsd != null && (
        <Chip tone="primary" title="x-tokenshield-cost-usd">
          Cost {formatUsd(h.costUsd)}
        </Chip>
      )}
      {h.estimatedCostUsd != null && (
        <Chip tone="neutral" title="x-tokenshield-estimated-cost-usd">
          Estimated {formatUsd(h.estimatedCostUsd)}
        </Chip>
      )}
      {h.avoidedCostUsd != null && h.avoidedCostUsd > 0 && (
        <Chip tone="savings" title="x-tokenshield-avoided-cost-usd">
          Avoided {formatUsd(h.avoidedCostUsd)}
        </Chip>
      )}
      {!h.priced && <Chip tone="warning">Unpriced</Chip>}
      {elapsedMs != null && <Chip tone="neutral">{formatLatency(elapsedMs)}</Chip>}
      {h.requestId && (
        <Link
          href={`/requests?id=${encodeURIComponent(h.requestId)}`}
          className="inline-flex h-5 items-center gap-1 rounded-full bg-neutral-soft px-2 font-mono text-[11px] text-muted-foreground hover:text-primary"
          title="Open in the request log"
        >
          {h.requestId}
          <ArrowUpRightIcon className="size-3" />
        </Link>
      )}
    </div>
  );
}

function DetailsTable({ details }: { details: Record<string, unknown> }) {
  const entries = Object.entries(details).filter(([k]) => k !== "errors");
  if (!entries.length) return null;
  return (
    <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg bg-card/70 px-3 py-2 text-[12px] dark:bg-background/40">
      {entries.map(([k, v]) => (
        <React.Fragment key={k}>
          <dt className="font-mono text-muted-foreground">{k}</dt>
          <dd className="min-w-0 truncate font-mono text-foreground">
            {typeof v === "number" && /usd|cost|remaining|estimate|limit_usd/i.test(k) ? formatUsd(v) : Array.isArray(v) ? v.join(", ") : String(v)}
          </dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function ErrorCard({ error }: { error: unknown }) {
  const api = error instanceof ApiError ? error : null;
  const headers = error instanceof PlaygroundError ? error.headers : null;
  const blocked = !!api && [402, 403, 422, 429].includes(api.status) && api.code !== "validation_error";
  const title = api ? (ERROR_TITLES[api.code] ?? (api.code === "validation_error" ? "Check the request" : ruleLabel(api.code) || "Request failed")) : "Request failed";
  const lines = api?.code === "validation_error" ? validationMessages(api.details) : [];
  return (
    <div className={cn("rounded-xl px-4 py-3.5", blocked ? "bg-warning-soft" : "bg-danger-soft")} role="alert">
      <div className="flex items-start gap-3">
        {blocked ? <BanIcon className="mt-0.5 size-4 shrink-0 text-warning" /> : <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-danger" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13.5px] font-semibold text-foreground">{title}</span>
            {api && (
              <Chip tone={blocked ? "warning" : "danger"} className="font-mono">
                {api.status} {api.code}
              </Chip>
            )}
          </div>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{lines.length ? lines.join(". ") : errorMessage(error)}</p>
          {blocked && <p className="mt-1 text-xs text-muted-foreground">TokenShield stopped this before the provider was called: nothing was spent.</p>}
          {api && <DetailsTable details={api.details} />}
          {headers?.requestId && (
            <div className="mt-3">
              <HeaderChips h={headers} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Answer({ result }: { result: PlaygroundResult }) {
  const choice = result.body.choices?.[0];
  const usage = result.body.usage;
  return (
    <div className="space-y-4">
      <HeaderChips h={result.headers} elapsedMs={result.elapsedMs} />
      <div className="rounded-xl bg-muted/60 px-4 py-3.5">
        <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-subtle uppercase">
          <SparklesIcon className="size-3.5" />
          Assistant
          {result.body.model && <span className="font-mono normal-case">{result.body.model}</span>}
        </div>
        <p className="text-[14px] leading-relaxed whitespace-pre-wrap text-foreground">{choice?.message?.content || "(empty response)"}</p>
        {choice?.finish_reason === "length" && (
          <p className="mt-2 text-xs text-warning">Stopped at the max tokens limit. Raise Max tokens for a complete answer.</p>
        )}
      </div>
      {usage && (
        <div className="grid grid-cols-3 gap-2 text-[12.5px]">
          {[
            { label: "Prompt tokens", value: usage.prompt_tokens },
            { label: "Cached tokens", value: usage.prompt_tokens_details?.cached_tokens ?? 0 },
            { label: "Completion tokens", value: usage.completion_tokens },
          ].map((u) => (
            <div key={u.label} className="rounded-xl bg-muted/60 px-3 py-2">
              <div className="text-[11px] text-subtle">{u.label}</div>
              <div className="text-[15px] font-semibold tabular">{formatNumber(u.value ?? 0)}</div>
            </div>
          ))}
        </div>
      )}
      {result.headers.cache === "MISS" && (
        <p className="text-xs text-muted-foreground">Stored in cache. Run the same request again with temperature 0 to see a cache hit and the spend it avoids.</p>
      )}
    </div>
  );
}

export function PlaygroundScreen() {
  const projects = useProjects();
  const models = useModels();
  const run = usePlaygroundRun();
  const { canWrite } = usePermissions();

  const [projectId, setProjectId] = React.useState("");
  const [model, setModel] = React.useState("");
  const [system, setSystem] = React.useState("You are a concise assistant.");
  const [user, setUser] = React.useState("Explain in two sentences why caching LLM responses saves money.");
  const [temperature, setTemperature] = React.useState("0");
  const [maxTokens, setMaxTokens] = React.useState("256");
  const [endUser, setEndUser] = React.useState("");
  const [taskId, setTaskId] = React.useState("");
  const [cache, setCache] = React.useState(true);
  const [formError, setFormError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!projectId && projects.data?.[0]) setProjectId(projects.data[0].id);
  }, [projects.data, projectId]);
  React.useEffect(() => {
    if (!model && models.data?.length) setModel((models.data.find((m) => m.alias === "chat-small" && m.enabled) ?? models.data.find((m) => m.enabled))?.alias ?? "");
  }, [models.data, model]);

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!projectId || !model) return setFormError("Pick a project and a model.");
    if (!user.trim()) return setFormError("Write a user message.");
    const t = Number(temperature);
    if (!Number.isFinite(t) || t < 0 || t > 2) return setFormError("Temperature must be between 0 and 2.");
    const mt = maxTokens.trim() ? Number(maxTokens) : null;
    if (mt != null && (!Number.isInteger(mt) || mt < 1)) return setFormError("Max tokens must be a whole number above 0, or empty.");
    setFormError(null);
    const messages: PlaygroundRequest["messages"] = [];
    if (system.trim()) messages.push({ role: "system", content: system.trim() });
    messages.push({ role: "user", content: user.trim() });
    run.mutate({
      project_id: projectId,
      model,
      messages,
      temperature: t,
      max_tokens: mt,
      end_user: endUser.trim() || null,
      task_id: taskId.trim() || null,
      cache: cache ? "on" : "off",
    });
  }

  if (!canWrite) {
    return (
      <>
        <PageHeader title="Playground" description="Send a request through the full gateway pipeline." />
        <div className="surface">
          <EmptyState
            icon={FlaskConicalIcon}
            title="The Playground needs an admin role"
            description="Playground requests are real gateway calls that spend budget, so viewers cannot run them. Ask an owner to upgrade your role, or browse past requests."
            action={
              <Link href="/requests" className={buttonVariants({ size: "sm" })}>
                Open the request log
              </Link>
            }
          />
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Playground"
        description="Send a chat completion through the full pipeline as a project: policies, budgets, cache and accounting all apply, and it lands in the request log."
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Surface>
          <SurfaceHeader title="Request" />
          <form
            onSubmit={submit}
            className="space-y-4 px-5 pb-5"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
            }}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Project" htmlFor="pg-project">
                <SimpleSelect
                  id="pg-project"
                  value={projectId}
                  onValueChange={setProjectId}
                  options={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
                  placeholder={projects.isPending ? "Loading..." : "Create a project first"}
                />
              </Field>
              <Field label="Model" htmlFor="pg-model">
                <SimpleSelect
                  id="pg-model"
                  value={model}
                  onValueChange={setModel}
                  options={(models.data ?? []).filter((m) => m.kind === "chat").map((m) => ({ value: m.alias, label: m.alias, disabled: !m.enabled }))}
                  placeholder={models.isPending ? "Loading..." : "No models"}
                />
              </Field>
            </div>
            <Field label="System message" htmlFor="pg-system">
              <Textarea id="pg-system" rows={2} value={system} onChange={(e) => setSystem(e.target.value)} />
            </Field>
            <Field label="User message" htmlFor="pg-user">
              <Textarea id="pg-user" rows={5} value={user} onChange={(e) => setUser(e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Temperature" htmlFor="pg-temp" hint="0 makes answers cacheable.">
                <Input id="pg-temp" inputMode="decimal" className="tabular" value={temperature} onChange={(e) => setTemperature(e.target.value)} />
              </Field>
              <Field label="Max tokens" htmlFor="pg-max" hint="Sets the worst-case cost reserved.">
                <Input id="pg-max" inputMode="numeric" className="tabular" value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} />
              </Field>
              <Field label="End user id" htmlFor="pg-user-id" hint="Optional: per-user budgets and cache scope.">
                <Input id="pg-user-id" className="font-mono text-[12.5px]" placeholder="student-0042" value={endUser} onChange={(e) => setEndUser(e.target.value)} />
              </Field>
              <Field label="Agent task id" htmlFor="pg-task" hint="Optional: counts toward task caps.">
                <Input id="pg-task" className="font-mono text-[12.5px]" placeholder="pr-4180" value={taskId} onChange={(e) => setTaskId(e.target.value)} />
              </Field>
            </div>
            <label className="flex items-center justify-between gap-4 rounded-xl bg-muted/60 px-3.5 py-2.5">
              <span>
                <span className="flex items-center gap-1.5 text-[13px] font-medium">
                  Use cache <Hint term="coalescing" />
                </span>
                <span className="block text-xs text-muted-foreground">Off sends x-tokenshield-cache: off, as a sensitive request would.</span>
              </span>
              <Switch checked={cache} onCheckedChange={setCache} aria-label="Use cache" />
            </label>
            {formError && <p className="text-xs font-medium text-danger">{formError}</p>}
            <div className="flex items-center justify-between gap-3">
              <span className="hidden text-xs text-faint sm:inline">Ctrl or Cmd + Enter to send</span>
              <Button type="submit" disabled={run.isPending} className="ml-auto">
                {run.isPending ? <LoaderIcon className="animate-spin" /> : <PlayIcon />}
                {run.isPending ? "Running..." : "Send request"}
              </Button>
            </div>
          </form>
        </Surface>

        <Surface className="h-fit">
          <SurfaceHeader title="Response" description="Answer plus the x-tokenshield-* headers the gateway returned" />
          <div className="px-5 pb-5">
            {run.isPending ? (
              <div className="flex items-center gap-3 rounded-xl bg-muted/60 px-4 py-6 text-[13px] text-muted-foreground">
                <LoaderIcon className="size-4 animate-spin" />
                Checking policies, reserving budget and calling the provider...
              </div>
            ) : run.isError ? (
              <ErrorCard error={run.error} />
            ) : run.data ? (
              <Answer result={run.data} />
            ) : (
              <EmptyState
                compact
                icon={FlaskConicalIcon}
                title="Nothing sent yet"
                description="Send a request to see the answer, its cost, the cache outcome and the request id. Try a huge Max tokens against a small budget to watch TokenShield block it."
              />
            )}
          </div>
        </Surface>
      </div>
    </>
  );
}
