"use client";

import { HistoryIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/errors";
import type { Model } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

import { usePrices, usePublishPrice } from "../api";

/** Per-1M prices come back as decimal strings; show them as $2.50. */
export function perMillion(value: string | null | undefined): string {
  if (value == null || value === "") return "n/a";
  const n = Number(value);
  if (!Number.isFinite(n)) return "n/a";
  if (n === 0) return "Free";
  return `$${n < 0.01 ? n.toPrecision(2) : n.toFixed(n < 1 ? 3 : 2).replace(/(\.\d\d)0$/, "$1")}`;
}

export function PriceHistorySheet({ model, onClose }: { model: Model | null; onClose: () => void }) {
  const q = usePrices(model?.id ?? null);
  return (
    <Sheet open={!!model} onOpenChange={(o) => !o && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle className="flex items-center gap-1.5">
            Price history <Hint term="priceVersion" />
          </SheetTitle>
          <SheetDescription>
            <span className="font-mono">{model?.alias}</span>, per 1M tokens. Usage rows keep the version they were charged at.
          </SheetDescription>
        </SheetHeader>
        <SheetBody>
          {q.isPending ? (
            <div className="space-y-2">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </div>
          ) : q.isError ? (
            <ErrorState error={q.error} onRetry={() => void q.refetch()} compact />
          ) : !q.data?.length ? (
            <EmptyState compact icon={HistoryIcon} title="Never priced" description="Publish a price so this model's spend is tracked and checked against hard budgets." />
          ) : (
            <ol className="space-y-2">
              {[...q.data]
                .sort((a, b) => b.version - a.version)
                .map((p, i) => (
                  <li key={p.id} className="rounded-xl bg-muted/60 px-4 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2 text-[13px] font-semibold">
                        Version {p.version}
                        {i === 0 && <Chip tone="success">Current</Chip>}
                      </span>
                      <span className="text-xs text-muted-foreground">{formatDateTime(p.effective_from)}</span>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-[12.5px] tabular">
                      <div>
                        <div className="text-[11px] text-subtle">Input</div>
                        {perMillion(p.input_per_m)}
                      </div>
                      <div>
                        <div className="text-[11px] text-subtle">Cached input</div>
                        {perMillion(p.cached_input_per_m)}
                      </div>
                      <div>
                        <div className="text-[11px] text-subtle">Output</div>
                        {perMillion(p.output_per_m)}
                      </div>
                    </div>
                    {p.note && <p className="mt-2 text-xs text-muted-foreground">{p.note}</p>}
                  </li>
                ))}
            </ol>
          )}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}

function money(raw: string, required: boolean): number | null | "invalid" {
  const t = raw.trim();
  if (!t) return required ? "invalid" : null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? n : "invalid";
}

export function PublishPriceDialog({ model, onClose }: { model: Model | null; onClose: () => void }) {
  const publish = usePublishPrice();
  const [input, setInput] = React.useState("");
  const [cached, setCached] = React.useState("");
  const [output, setOutput] = React.useState("");
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (model) {
      setInput(model.price ? String(Number(model.price.input_per_m)) : "");
      setCached(model.price?.cached_input_per_m ? String(Number(model.price.cached_input_per_m)) : "");
      setOutput(model.price ? String(Number(model.price.output_per_m)) : "");
      setNote("");
      setError(null);
    }
  }, [model]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const i = money(input, true);
    const c = money(cached, false);
    const o = money(output, true);
    if (i === "invalid" || o === "invalid" || c === "invalid") {
      setError("Enter input and output prices as numbers of 0 or more. Cached input is optional.");
      return;
    }
    if (!model) return;
    publish.mutate(
      { modelId: model.id, body: { input_per_m: i ?? 0, output_per_m: o ?? 0, cached_input_per_m: c, note: note.trim() } },
      {
        onSuccess: (p) => {
          toast.success(`Price v${p.version} published for ${model.alias}. New requests use it now.`);
          onClose();
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={!!model} onOpenChange={(o) => !o && !publish.isPending && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Publish a new price</DialogTitle>
          <DialogDescription>
            For <span className="font-mono text-foreground">{model?.alias}</span>, in USD per 1M tokens. Past requests keep the price they were charged.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <Field label="Input" htmlFor="price-in">
                <Input id="price-in" inputMode="decimal" className="tabular" value={input} onChange={(e) => setInput(e.target.value)} placeholder="2.50" />
              </Field>
              <Field label="Cached input" htmlFor="price-cached">
                <Input id="price-cached" inputMode="decimal" className="tabular" value={cached} onChange={(e) => setCached(e.target.value)} placeholder="Optional" />
              </Field>
              <Field label="Output" htmlFor="price-out">
                <Input id="price-out" inputMode="decimal" className="tabular" value={output} onChange={(e) => setOutput(e.target.value)} placeholder="10.00" />
              </Field>
            </div>
            <Field label="Note" htmlFor="price-note" hint="Optional, e.g. the provider's price page date.">
              <Input id="price-note" value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={publish.isPending}>
              {publish.isPending ? "Publishing..." : "Publish price"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
