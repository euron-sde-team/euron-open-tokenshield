"use client";

import * as React from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/segmented";
import { ToggleChips } from "@/components/toggle-chips";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { ScopePicker } from "@/features/budgets/components/scope-picker";
import { useModels } from "@/features/models/api";
import { errorMessage } from "@/lib/api/errors";
import type { Rule, RuleAction, RuleKind, RuleScopeType } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { ACTION_LABEL, buildParams, paramsToForm, RULE_KINDS, ruleKindSpec } from "@/lib/policies";

import { useCreatePolicy, useUpdatePolicy } from "../api";
import { RuleIcon } from "./rule-icon";

const RULE_SCOPES: { value: RuleScopeType; label: string }[] = [
  { value: "global", label: "Whole gateway" },
  { value: "team", label: "Team" },
  { value: "project", label: "Project" },
  { value: "api_key", label: "API key" },
  { value: "model", label: "Model" },
];

function defaultsFor(kind: RuleKind) {
  const spec = ruleKindSpec(kind);
  return paramsToForm(kind, spec?.defaults ?? {});
}

export function PolicyDialog({ open, onOpenChange, rule }: { open: boolean; onOpenChange: (o: boolean) => void; rule?: Rule | null }) {
  const editing = !!rule;
  const models = useModels();
  const create = useCreatePolicy();
  const update = useUpdatePolicy();
  const pending = create.isPending || update.isPending;

  const [kind, setKind] = React.useState<RuleKind>("max_input_tokens");
  const [name, setName] = React.useState("");
  const [action, setAction] = React.useState<RuleAction>("reject");
  const [scopeType, setScopeType] = React.useState<RuleScopeType>("global");
  const [scopeId, setScopeId] = React.useState("");
  const [form, setForm] = React.useState<Record<string, string>>({});
  const [modelList, setModelList] = React.useState<string[]>([]);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [serverError, setServerError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    const k = (rule?.kind as RuleKind) ?? "max_input_tokens";
    setKind(k);
    setName(rule?.name ?? "");
    setAction((rule?.action as RuleAction) ?? ruleKindSpec(k)?.defaultAction ?? "reject");
    setScopeType((rule?.scope_type as RuleScopeType) ?? "global");
    setScopeId(rule?.scope_id ?? "");
    const f = rule ? paramsToForm(k, rule.params) : defaultsFor(k);
    setForm(f.form);
    setModelList(f.models);
    setErrors({});
    setServerError(null);
  }, [open, rule]);

  const spec = ruleKindSpec(kind);

  function pickKind(k: RuleKind) {
    setKind(k);
    const s = ruleKindSpec(k);
    setAction(s?.defaultAction ?? "reject");
    const f = defaultsFor(k);
    setForm(f.form);
    setModelList(f.models);
    setErrors({});
    if (!name.trim() || RULE_KINDS.some((r) => r.label === name)) setName(s?.label ?? "");
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const { params, errors: errs } = buildParams(kind, form, modelList);
    if (!name.trim()) errs.name = "Name the rule so alerts and rejections are recognisable.";
    if (scopeType !== "global" && !scopeId) errs.scope = "Pick what this rule applies to.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setServerError(null);
    const done = {
      onSuccess: () => {
        toast.success(editing ? "Rule updated." : "Rule created. It applies to the next request.");
        onOpenChange(false);
      },
      onError: (err: unknown) => setServerError(errorMessage(err)),
    };
    if (editing && rule) update.mutate({ id: rule.id, body: { name: name.trim(), params, action } }, done);
    else
      create.mutate(
        { name: name.trim(), kind, action, params, scope_type: scopeType, scope_id: scopeType === "global" ? null : scopeId, enabled: true },
        done,
      );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit rule" : "New policy rule"}</DialogTitle>
          <DialogDescription>Rules run on every request before any budget is reserved or provider called.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-5">
            {!editing && (
              <div role="radiogroup" aria-label="Rule type" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {RULE_KINDS.map((k) => (
                  <button
                    key={k.kind}
                    type="button"
                    role="radio"
                    aria-checked={kind === k.kind}
                    onClick={() => pickKind(k.kind)}
                    className={cn(
                      "flex items-start gap-2.5 rounded-xl bg-muted/60 p-3 text-left transition-[background-color,box-shadow] hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring",
                      kind === k.kind && "bg-primary-soft ring-2 ring-primary/50 hover:bg-primary-soft",
                    )}
                  >
                    <RuleIcon kind={k.kind} className="size-8 bg-card dark:bg-background" />
                    <span className="min-w-0">
                      <span className="block text-[13px] font-semibold">{k.label}</span>
                      <span className="mt-0.5 block text-[11.5px] leading-snug text-muted-foreground">{k.description}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
            {editing && spec && (
              <div className="flex items-center gap-3 rounded-xl bg-muted/60 p-3">
                <RuleIcon kind={kind} />
                <div>
                  <div className="text-[13px] font-semibold">{spec.label}</div>
                  <div className="text-xs text-muted-foreground">{spec.description}</div>
                </div>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name" htmlFor="rule-name" error={errors.name}>
                <Input id="rule-name" value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Field label="Action" hint={action === "alert" ? "Lets the request through and raises an alert." : undefined}>
                <Segmented
                  ariaLabel="Action"
                  value={action}
                  onChange={setAction}
                  options={(spec?.actions ?? []).map((a) => ({ value: a, label: ACTION_LABEL[a] }))}
                />
              </Field>
            </div>

            {spec && spec.fields.length > 0 && (
              <div className="grid gap-4 sm:grid-cols-2">
                {spec.fields.map((f) =>
                  f.type === "models" ? (
                    <Field key={f.key} label={f.label} hint={f.hint} error={errors[f.key]} className="sm:col-span-2">
                      <ToggleChips
                        ariaLabel={f.label}
                        options={(models.data ?? []).map((m) => ({ value: m.alias, label: m.alias }))}
                        value={modelList}
                        onChange={setModelList}
                      />
                    </Field>
                  ) : f.type === "patterns" ? (
                    <Field key={f.key} label={f.label} hint={f.hint} error={errors[f.key]} htmlFor={`rule-${f.key}`} className="sm:col-span-2">
                      <Textarea
                        id={`rule-${f.key}`}
                        className="font-mono text-[12.5px]"
                        rows={4}
                        placeholder={"ignore (all )?previous instructions\nreveal your system prompt"}
                        value={form[f.key] ?? ""}
                        onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                      />
                    </Field>
                  ) : (
                    <Field key={f.key} label={f.label} hint={f.hint} error={errors[f.key]} htmlFor={`rule-${f.key}`}>
                      <Input
                        id={`rule-${f.key}`}
                        inputMode={f.type === "usd" ? "decimal" : "numeric"}
                        className="tabular"
                        placeholder={f.required ? undefined : "No cap"}
                        value={form[f.key] ?? ""}
                        onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                      />
                    </Field>
                  ),
                )}
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Applies to" htmlFor="rule-scope" hint={editing ? "Scope is fixed once created." : undefined}>
                <SimpleSelect
                  id="rule-scope"
                  value={scopeType}
                  disabled={editing}
                  onValueChange={(v) => {
                    setScopeType((v || "global") as RuleScopeType);
                    setScopeId("");
                  }}
                  options={RULE_SCOPES}
                />
              </Field>
              {scopeType !== "global" && (
                <ScopePicker scopeType={scopeType} value={scopeId} onChange={setScopeId} disabled={editing} error={errors.scope} />
              )}
            </div>
            {serverError && <FieldError>{serverError}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={pending}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Saving..." : editing ? "Save changes" : "Create rule"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
