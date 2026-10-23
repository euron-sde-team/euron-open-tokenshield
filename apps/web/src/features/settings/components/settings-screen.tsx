"use client";

import { CheckCircle2Icon, XCircleIcon } from "lucide-react";
import * as React from "react";

import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Surface, SurfaceHeader } from "@/components/surface";
import { ThemeSelector } from "@/components/theme-toggle";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/features/auth/api";
import { ChangePasswordForm } from "@/features/auth/components/change-password-dialog";
import { roleDescription, roleLabel } from "@/lib/roles";

import { useSystemInfo } from "../api";

function Row({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <div>
        <div className="text-[13px] text-muted-foreground">{label}</div>
        {hint && <div className="text-[11.5px] text-faint">{hint}</div>}
      </div>
      <div className="text-right text-[13px] font-medium">{value}</div>
    </div>
  );
}

export function SettingsScreen() {
  const q = useSystemInfo();
  const { user } = usePermissions();
  const checks = (q.data?.checks ?? {}) as Record<string, { ok?: boolean; ms?: number }>;

  return (
    <>
      <PageHeader title="Settings" description="How this TokenShield install is configured, plus your own account preferences." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Surface>
          <SurfaceHeader title="System" description="Read from the running API. Change it through environment variables." />
          <div className="px-5 pb-4">
            {q.isPending ? (
              <div className="space-y-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-5" />
                ))}
              </div>
            ) : q.isError ? (
              <ErrorState error={q.error} onRetry={() => void q.refetch()} compact />
            ) : (
              <div className="divide-y divide-hairline">
                <Row label="Version" value={<span className="font-mono">v{q.data.version}</span>} />
                <Row label="Environment" value={<Chip tone={q.data.environment === "production" ? "success" : "info"} className="capitalize">{q.data.environment}</Chip>} />
                <Row label="Cloud" value={<span className="capitalize">{q.data.cloud}</span>} />
                <Row label="Provider key sealing" value={<span className="uppercase">{q.data.key_mode}</span>} hint="How provider API keys are encrypted at rest." />
                <Row label="Export storage" value={<span className="uppercase">{q.data.storage}</span>} />
                <Row
                  label="Budget store failure mode"
                  value={<Chip tone={q.data.budget_failure_mode === "closed" ? "success" : "warning"}>Fail {q.data.budget_failure_mode}</Chip>}
                  hint="Closed: if Redis is down, hard-budget requests get 503 instead of passing unchecked."
                />
                <Row label="Semantic cache" value={q.data.semantic_cache ? "Enabled" : "Off"} />
                <Row label="Store prompt content" value={q.data.store_content ? "Yes" : "No, metadata only"} hint="Whether prompt excerpts are kept with usage events." />
                <Row label="Inventory" value={`${q.data.projects} projects · ${q.data.models} models · ${q.data.active_keys} active keys`} />
                <div className="pt-3">
                  <div className="mb-2 text-[13px] text-muted-foreground">Dependencies</div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(checks).map(([name, c]) => (
                      <span key={name} className="inline-flex items-center gap-1.5 rounded-lg bg-muted px-2.5 py-1.5 text-[12.5px]">
                        {c?.ok ? <CheckCircle2Icon className="size-3.5 text-savings" /> : <XCircleIcon className="size-3.5 text-danger" />}
                        <span className="capitalize">{name}</span>
                        {c?.ms != null && <span className="text-subtle tabular">{c.ms} ms</span>}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </Surface>
        <div className="flex flex-col gap-4">
          <Surface>
            <SurfaceHeader title="Your account" />
            <div className="divide-y divide-hairline px-5 pb-4">
              <Row label="Name" value={user?.name} />
              <Row label="Email" value={user?.email} />
              <Row label="Role" value={<Chip tone="primary">{roleLabel(user?.role)}</Chip>} hint={roleDescription(user?.role)} />
            </div>
          </Surface>
          <Surface>
            <SurfaceHeader title="Appearance" description="Saved in this browser." />
            <div className="px-5 pb-5">
              <ThemeSelector />
            </div>
          </Surface>
          <Surface>
            <SurfaceHeader title="Change password" description="Other sessions are signed out when it changes." />
            <div className="px-5 pb-5">
              <ChangePasswordForm footer="inline" />
            </div>
          </Surface>
        </div>
      </div>
    </>
  );
}
