import { BotIcon, FileWarningIcon, LockIcon, MaximizeIcon, RepeatIcon, ScanTextIcon, ShieldIcon } from "lucide-react";

import { cn } from "@/lib/cn";

const ICONS = {
  max_input_tokens: MaximizeIcon,
  max_output_tokens: FileWarningIcon,
  restricted_model: LockIcon,
  prompt_injection: ScanTextIcon,
  retry_storm: RepeatIcon,
  agent_task: BotIcon,
} as const;

export function RuleIcon({ kind, className }: { kind: string; className?: string }) {
  const Icon = ICONS[kind as keyof typeof ICONS] ?? ShieldIcon;
  return (
    <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary", className)}>
      <Icon className="size-4" />
    </span>
  );
}
