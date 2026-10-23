"use client";

import { Chip } from "@/components/ui/chip";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cacheChip, statusChip, type ChipSpec } from "@/lib/chips";

function SpecChip({ spec, withHint = true }: { spec: ChipSpec; withHint?: boolean }) {
  const chip = (
    <Chip tone={spec.tone} dot>
      {spec.label}
    </Chip>
  );
  if (!withHint || !spec.hint) return chip;
  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} className="inline-flex rounded-full focus-visible:outline-2 focus-visible:outline-ring" />}>
        {chip}
      </TooltipTrigger>
      <TooltipContent>{spec.hint}</TooltipContent>
    </Tooltip>
  );
}

export function StatusChip({ status, withHint }: { status: string | null | undefined; withHint?: boolean }) {
  return <SpecChip spec={statusChip(status)} withHint={withHint} />;
}

export function CacheChip({ status, withHint }: { status: string | null | undefined; withHint?: boolean }) {
  return <SpecChip spec={cacheChip(status)} withHint={withHint} />;
}
