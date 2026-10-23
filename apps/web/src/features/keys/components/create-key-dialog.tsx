"use client";

import { CheckCircle2Icon, TriangleAlertIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { CodeBlock } from "@/components/code-block";
import { CopyButton } from "@/components/copy-button";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { useProjects } from "@/features/projects/api";
import { errorMessage } from "@/lib/api/errors";
import type { ApiKeyCreated } from "@/lib/api/types";
import { curlSnippet, gatewayBaseUrl, nodeSnippet, pythonSnippet } from "@/lib/snippets";

import { useCreateKey } from "../api";

function optionalInt(raw: string): number | null | "invalid" {
  const t = raw.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isInteger(n) && n > 0 ? n : "invalid";
}

export function KeyRevealed({ created }: { created: ApiKeyCreated }) {
  const [origin, setOrigin] = React.useState("");
  React.useEffect(() => setOrigin(window.location.origin), []);
  return (
    <div className="space-y-4">
      <div className="flex gap-3 rounded-xl bg-warning-soft px-4 py-3 text-[13px]">
        <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-warning" />
        <p className="text-foreground">
          Copy this key now. It is shown <strong>once</strong>; TokenShield stores only a peppered hash and cannot show it again.
        </p>
      </div>
      <div className="flex items-center gap-2 rounded-xl bg-muted p-1.5 pl-3.5">
        <code className="min-w-0 flex-1 truncate font-mono text-[12.5px] select-all" data-testid="new-key">
          {created.key}
        </code>
        <CopyButton value={created.key} label="Copy key" variant="default" />
      </div>
      <div>
        <p className="mb-2 text-[13px] text-muted-foreground">
          Point any OpenAI client at <code className="font-mono text-[12px] text-foreground">{gatewayBaseUrl(origin)}</code>:
        </p>
        <CodeBlock
          samples={[
            { id: "curl", label: "curl", code: curlSnippet(origin, created.key) },
            { id: "python", label: "Python", code: pythonSnippet(origin, created.key) },
            { id: "node", label: "Node", code: nodeSnippet(origin, created.key) },
          ]}
        />
      </div>
    </div>
  );
}

export function CreateKeyDialog({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId?: string;
}) {
  const projects = useProjects();
  const create = useCreateKey();
  const [project, setProject] = React.useState(projectId ?? "");
  const [name, setName] = React.useState("");
  const [rpm, setRpm] = React.useState("");
  const [tpm, setTpm] = React.useState("");
  const [conc, setConc] = React.useState("");
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [serverError, setServerError] = React.useState<string | null>(null);
  const [created, setCreated] = React.useState<ApiKeyCreated | null>(null);

  React.useEffect(() => {
    if (open) {
      setProject(projectId ?? "");
      setName("");
      setRpm("");
      setTpm("");
      setConc("");
      setErrors({});
      setServerError(null);
      setCreated(null);
    }
  }, [open, projectId]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!project) errs.project = "Pick the project this key bills to.";
    if (!name.trim()) errs.name = "Name it after where it runs, for example \"production\".";
    const r = optionalInt(rpm);
    const t = optionalInt(tpm);
    const c = optionalInt(conc);
    if (r === "invalid") errs.rpm = "Whole number above 0, or empty.";
    if (t === "invalid") errs.tpm = "Whole number above 0, or empty.";
    if (c === "invalid") errs.conc = "Whole number above 0, or empty.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setServerError(null);
    create.mutate(
      {
        project_id: project,
        name: name.trim(),
        rpm_limit: r === "invalid" ? null : r,
        tpm_limit: t === "invalid" ? null : t,
        concurrency_limit: c === "invalid" ? null : c,
      },
      {
        onSuccess: (k) => {
          setCreated(k);
          toast.success("API key created.");
        },
        onError: (err) => setServerError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent className={created ? "max-w-2xl" : "max-w-lg"}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {created && <CheckCircle2Icon className="size-5 text-savings" />}
            {created ? `Key "${created.name}" is ready` : "New API key"}
          </DialogTitle>
          <DialogDescription>
            {created
              ? `Bills to ${created.project_name ?? "its project"}. Revoke it any time from API keys.`
              : "Applications use this key instead of a provider key. Spend is attributed to its project."}
          </DialogDescription>
        </DialogHeader>
        {created ? (
          <>
            <DialogBody>
              <KeyRevealed created={created} />
            </DialogBody>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>I have copied the key</Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
            <DialogBody className="space-y-4">
              {!projectId && (
                <Field label="Project" htmlFor="key-project" error={errors.project}>
                  <SimpleSelect
                    id="key-project"
                    value={project}
                    onValueChange={setProject}
                    placeholder={projects.data?.length ? "Choose a project" : "Create a project first"}
                    options={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
                  />
                </Field>
              )}
              <Field label="Name" htmlFor="key-name" error={errors.name}>
                <Input id="key-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="production" />
              </Field>
              <div>
                <div className="mb-2 text-[13px] font-medium">Limits</div>
                <div className="grid grid-cols-3 gap-3">
                  <Field label={<span className="text-xs text-muted-foreground">Requests / min</span>} htmlFor="key-rpm" error={errors.rpm}>
                    <Input id="key-rpm" inputMode="numeric" className="tabular" placeholder="None" value={rpm} onChange={(e) => setRpm(e.target.value)} />
                  </Field>
                  <Field label={<span className="text-xs text-muted-foreground">Tokens / min</span>} htmlFor="key-tpm" error={errors.tpm}>
                    <Input id="key-tpm" inputMode="numeric" className="tabular" placeholder="None" value={tpm} onChange={(e) => setTpm(e.target.value)} />
                  </Field>
                  <Field label={<span className="text-xs text-muted-foreground">Concurrent</span>} htmlFor="key-conc" error={errors.conc}>
                    <Input id="key-conc" inputMode="numeric" className="tabular" placeholder="None" value={conc} onChange={(e) => setConc(e.target.value)} />
                  </Field>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">Over a limit, requests get HTTP 429 with Retry-After and the limit named.</p>
              </div>
              {serverError && <FieldError>{serverError}</FieldError>}
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Creating..." : "Create key"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
