"use client";

import * as React from "react";
import { toast } from "sonner";

import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/types";

import { useCreateProvider, useUpdateProvider } from "../api";

export function ProviderDialog({ open, onOpenChange, provider }: { open: boolean; onOpenChange: (o: boolean) => void; provider?: Provider | null }) {
  const editing = !!provider;
  const create = useCreateProvider();
  const update = useUpdateProvider();
  const pending = create.isPending || update.isPending;
  const [name, setName] = React.useState("");
  const [kind, setKind] = React.useState<"openai" | "anthropic">("openai");
  const [baseUrl, setBaseUrl] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [timeout, setTimeoutS] = React.useState("30");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setName(provider?.name ?? "");
    setKind((provider?.kind as "openai" | "anthropic") ?? "openai");
    setBaseUrl(provider?.base_url ?? "https://api.openai.com/v1");
    setApiKey("");
    setTimeoutS(provider?.timeout_s != null ? String(provider.timeout_s) : "30");
    setError(null);
  }, [open, provider]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("Name the provider, for example \"OpenAI production\".");
    try {
      new URL(baseUrl);
    } catch {
      return setError("Enter the full base URL, including http:// or https://.");
    }
    const t = Number(timeout);
    if (!Number.isFinite(t) || t <= 0) return setError("Timeout must be a number of seconds above 0.");
    setError(null);
    const done = {
      onSuccess: () => {
        toast.success(editing ? "Provider updated." : "Provider added. Add models that use it under Models.");
        onOpenChange(false);
      },
      onError: (err: unknown) => setError(errorMessage(err)),
    };
    if (editing && provider)
      update.mutate({ id: provider.id, body: { name: name.trim(), base_url: baseUrl.trim(), timeout_s: t, ...(apiKey ? { api_key: apiKey } : {}) } }, done);
    else create.mutate({ name: name.trim(), kind, base_url: baseUrl.trim(), api_key: apiKey || null, timeout_s: t, enabled: true }, done);
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{editing ? "Edit provider" : "Add provider"}</DialogTitle>
          <DialogDescription>
            The upstream TokenShield forwards to. Keys are sealed with KMS and never returned by the API.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <Field label="Name" htmlFor="prov-name">
              <Input id="prov-name" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="API style" hint={editing ? "Fixed once created." : "OpenAI-compatible also covers Ollama, vLLM, LM Studio and Groq."}>
              <Segmented
                ariaLabel="API style"
                value={kind}
                disabled={editing}
                onChange={(k) => {
                  setKind(k);
                  if (!editing) setBaseUrl(k === "anthropic" ? "https://api.anthropic.com" : "https://api.openai.com/v1");
                }}
                options={[
                  { value: "openai", label: "OpenAI-compatible" },
                  { value: "anthropic", label: "Anthropic" },
                ]}
              />
            </Field>
            <Field label="Base URL" htmlFor="prov-url">
              <Input id="prov-url" className="font-mono text-[12.5px]" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
              <Field
                label="API key"
                htmlFor="prov-key"
                hint={editing ? (provider?.has_key ? `Stored (${provider.key_hint ?? "sealed"}). Leave empty to keep it.` : "None stored.") : "Write only. Leave empty for keyless local servers."}
              >
                <Input id="prov-key" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={editing ? "Unchanged" : "sk-..."} />
              </Field>
              <Field label="Timeout (s)" htmlFor="prov-timeout">
                <Input id="prov-timeout" inputMode="decimal" className="tabular" value={timeout} onChange={(e) => setTimeoutS(e.target.value)} />
              </Field>
            </div>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Saving..." : editing ? "Save changes" : "Add provider"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
