"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/api/errors";

import { useCreateModel, useProviders } from "../api";

export function ModelDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const providers = useProviders();
  const create = useCreateModel();
  const [alias, setAlias] = React.useState("");
  const [providerId, setProviderId] = React.useState("");
  const [upstream, setUpstream] = React.useState("");
  const [ctx, setCtx] = React.useState("128000");
  const [maxOut, setMaxOut] = React.useState("8192");
  const [restricted, setRestricted] = React.useState(false);
  const [pin, setPin] = React.useState("");
  const [pout, setPout] = React.useState("");
  const [pcached, setPcached] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setAlias("");
      setProviderId(providers.data?.[0]?.id ?? "");
      setUpstream("");
      setCtx("128000");
      setMaxOut("8192");
      setRestricted(false);
      setPin("");
      setPout("");
      setPcached("");
      setError(null);
    }
  }, [open, providers.data]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!/^[a-z0-9][a-z0-9._-]*$/i.test(alias.trim())) return setError("Alias: letters, numbers, dots, dashes or underscores. Clients send this as the model.");
    if (!providerId) return setError("Pick a provider.");
    if (!upstream.trim()) return setError("Enter the provider's model name, e.g. gpt-4o-mini.");
    const c = Number(ctx);
    const m = Number(maxOut);
    if (!Number.isInteger(c) || c <= 0 || !Number.isInteger(m) || m <= 0) return setError("Context window and max output must be whole numbers.");
    const hasPrice = pin.trim() !== "" || pout.trim() !== "";
    if (hasPrice && (!Number.isFinite(Number(pin)) || !Number.isFinite(Number(pout)) || pin.trim() === "" || pout.trim() === ""))
      return setError("For a price, enter both input and output per 1M tokens.");
    setError(null);
    create.mutate(
      {
        alias: alias.trim(),
        provider_id: providerId,
        upstream_model: upstream.trim(),
        context_window: c,
        max_output_tokens: m,
        restricted,
        enabled: true,
        price: hasPrice ? { input_per_m: Number(pin), output_per_m: Number(pout), cached_input_per_m: pcached.trim() ? Number(pcached) : null } : null,
      },
      {
        onSuccess: (model) => {
          toast.success(model.price ? `Model ${model.alias} added.` : `Model ${model.alias} added without a price. Publish one before hard budgets apply.`);
          onOpenChange(false);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add model</DialogTitle>
          <DialogDescription>An alias clients request, mapped to a provider&apos;s model. Swap the upstream later without touching client code.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Alias" htmlFor="m-alias">
                <Input id="m-alias" className="font-mono text-[12.5px]" value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="chat-fast" />
              </Field>
              <Field label="Provider" htmlFor="m-provider">
                <SimpleSelect id="m-provider" value={providerId} onValueChange={setProviderId} options={(providers.data ?? []).map((p) => ({ value: p.id, label: p.name }))} placeholder="Choose" />
              </Field>
            </div>
            <Field label="Upstream model" htmlFor="m-upstream">
              <Input id="m-upstream" className="font-mono text-[12.5px]" value={upstream} onChange={(e) => setUpstream(e.target.value)} placeholder="gpt-4o-mini" />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Context window" htmlFor="m-ctx">
                <Input id="m-ctx" inputMode="numeric" className="tabular" value={ctx} onChange={(e) => setCtx(e.target.value)} />
              </Field>
              <Field label="Max output tokens" htmlFor="m-max">
                <Input id="m-max" inputMode="numeric" className="tabular" value={maxOut} onChange={(e) => setMaxOut(e.target.value)} />
              </Field>
            </div>
            <div>
              <div className="mb-2 text-[13px] font-medium">Price per 1M tokens (USD)</div>
              <div className="grid grid-cols-3 gap-3">
                <Input aria-label="Input price" inputMode="decimal" className="tabular" placeholder="Input" value={pin} onChange={(e) => setPin(e.target.value)} />
                <Input aria-label="Cached input price" inputMode="decimal" className="tabular" placeholder="Cached" value={pcached} onChange={(e) => setPcached(e.target.value)} />
                <Input aria-label="Output price" inputMode="decimal" className="tabular" placeholder="Output" value={pout} onChange={(e) => setPout(e.target.value)} />
              </div>
              <p className="mt-1.5 text-xs text-muted-foreground">Without a price the model is flagged unpriced: never treated as free, and blocked by hard budgets.</p>
            </div>
            <label className="flex items-center justify-between gap-4 rounded-xl bg-muted/60 px-3.5 py-2.5">
              <span>
                <span className="block text-[13px] font-medium">Restricted</span>
                <span className="block text-xs text-muted-foreground">Only projects that explicitly allow it may call it.</span>
              </span>
              <Switch checked={restricted} onCheckedChange={setRestricted} />
            </label>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Adding..." : "Add model"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
