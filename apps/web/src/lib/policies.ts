import type { RuleAction, RuleKind } from "./api/types";
import { formatDuration, formatNumber, formatUsd } from "./format";

export type ParamValue = number | string | string[] | undefined;
export type RuleParams = Record<string, ParamValue>;

export interface ParamField {
  key: string;
  label: string;
  type: "int" | "usd" | "models" | "patterns";
  hint: string;
  required: boolean;
  min?: number;
}

export interface RuleKindSpec {
  kind: RuleKind;
  label: string;
  description: string;
  actions: RuleAction[];
  defaultAction: RuleAction;
  fields: ParamField[];
  defaults: RuleParams;
}

/** Which actions each rule kind supports (mirrors the API's validation). */
export const RULE_KINDS: RuleKindSpec[] = [
  {
    kind: "max_input_tokens",
    label: "Oversized prompt",
    description: "Stop prompts larger than a token limit before they are sent.",
    actions: ["reject", "alert"],
    defaultAction: "reject",
    fields: [{ key: "limit", label: "Max input tokens", type: "int", hint: "Estimated prompt tokens per request.", required: true, min: 1 }],
    defaults: { limit: 24000 },
  },
  {
    kind: "max_output_tokens",
    label: "Excessive output",
    description: "Limit how many tokens a response may produce. Cap lowers max_tokens instead of rejecting.",
    actions: ["reject", "cap", "alert"],
    defaultAction: "cap",
    fields: [
      {
        key: "limit",
        label: "Max output tokens",
        type: "int",
        hint: "Requests asking for more trigger the rule. With Cap, max_tokens is lowered to this value.",
        required: true,
        min: 1,
      },
    ],
    defaults: { limit: 2048 },
  },
  {
    kind: "restricted_model",
    label: "Restricted model",
    description: "Block or flag use of specific models in this scope.",
    actions: ["reject", "alert"],
    defaultAction: "reject",
    fields: [{ key: "models", label: "Models", type: "models", hint: "Requests to any of these models trigger the rule.", required: true }],
    defaults: { models: [] },
  },
  {
    kind: "prompt_injection",
    label: "Prompt injection",
    description: "Match user messages against injection phrases: the built-in list, or your own.",
    actions: ["reject", "alert"],
    defaultAction: "alert",
    fields: [
      {
        key: "patterns",
        label: "Extra patterns",
        type: "patterns",
        hint: "Optional. One regular expression per line. When set, these replace the built-in list.",
        required: false,
      },
    ],
    defaults: {},
  },
  {
    kind: "retry_storm",
    label: "Retry storm",
    description: "Throttle the same request repeated too often in a short window.",
    actions: ["throttle", "alert"],
    defaultAction: "throttle",
    fields: [
      { key: "max_repeats", label: "Max repeats", type: "int", hint: "Identical requests allowed inside the window.", required: true, min: 1 },
      { key: "window_s", label: "Window (seconds)", type: "int", hint: "Sliding window length.", required: true, min: 1 },
    ],
    defaults: { max_repeats: 6, window_s: 60 },
  },
  {
    kind: "agent_task",
    label: "Agent task caps",
    description: "Stop runaway agent loops, keyed by the x-tokenshield-task-id header.",
    actions: ["reject", "alert"],
    defaultAction: "reject",
    fields: [
      { key: "max_calls", label: "Max calls", type: "int", hint: "Model calls per task.", required: false, min: 1 },
      { key: "max_cost_usd", label: "Max cost (USD)", type: "usd", hint: "Total spend per task.", required: false },
      { key: "max_repeated_tool_calls", label: "Max repeated tool calls", type: "int", hint: "Consecutive identical tool calls.", required: false, min: 1 },
      { key: "deadline_s", label: "Deadline (seconds)", type: "int", hint: "Time from the first call.", required: false, min: 1 },
    ],
    defaults: { max_calls: 25, max_cost_usd: 1, max_repeated_tool_calls: 3, deadline_s: 900 },
  },
];

export const ACTION_LABEL: Record<RuleAction, string> = {
  reject: "Reject",
  cap: "Cap",
  throttle: "Throttle",
  alert: "Alert only",
};

export function ruleKindSpec(kind: string): RuleKindSpec | undefined {
  return RULE_KINDS.find((k) => k.kind === kind);
}

export function isActionValid(kind: string, action: string): boolean {
  return !!ruleKindSpec(kind)?.actions.includes(action as RuleAction);
}

function num(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

/** One line describing a rule's parameters, e.g. "max 6 repeats in 60 s". */
export function paramsSummary(kind: string, params: Record<string, unknown>): string {
  switch (kind) {
    case "max_input_tokens":
      return num(params.limit) != null ? `over ${formatNumber(num(params.limit))} input tokens` : "no limit set";
    case "max_output_tokens":
      return num(params.limit) != null ? `over ${formatNumber(num(params.limit))} output tokens` : "no limit set";
    case "restricted_model": {
      const models = Array.isArray(params.models) ? (params.models as string[]) : [];
      return models.length ? models.join(", ") : "no models listed";
    }
    case "prompt_injection": {
      const patterns = Array.isArray(params.patterns) ? (params.patterns as string[]) : [];
      return patterns.length ? `${patterns.length} custom pattern${patterns.length === 1 ? "" : "s"}` : "built-in pattern list";
    }
    case "retry_storm":
      return `max ${num(params.max_repeats) ?? "?"} repeats in ${formatDuration(num(params.window_s) ?? 0)}`;
    case "agent_task": {
      const parts: string[] = [];
      if (num(params.max_calls) != null) parts.push(`${num(params.max_calls)} calls`);
      if (num(params.max_cost_usd) != null) parts.push(formatUsd(num(params.max_cost_usd)));
      if (num(params.max_repeated_tool_calls) != null) parts.push(`${num(params.max_repeated_tool_calls)} repeated tool calls`);
      if (num(params.deadline_s) != null) parts.push(`${formatDuration(num(params.deadline_s))} deadline`);
      return parts.length ? parts.join(" · ") : "no caps set";
    }
    default:
      return Object.keys(params).length ? JSON.stringify(params) : "";
  }
}

/** Form state (strings) to API params, with validation errors keyed by field. */
export function buildParams(kind: string, form: Record<string, string>, models: string[]): { params: RuleParams; errors: Record<string, string> } {
  const spec = ruleKindSpec(kind);
  const params: RuleParams = {};
  const errors: Record<string, string> = {};
  if (!spec) return { params, errors: { kind: "Pick a rule type." } };
  for (const f of spec.fields) {
    if (f.type === "models") {
      if (f.required && !models.length) errors[f.key] = "Choose at least one model.";
      else params[f.key] = models;
      continue;
    }
    if (f.type === "patterns") {
      const lines = (form[f.key] ?? "")
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean);
      if (lines.length) params[f.key] = lines;
      continue;
    }
    const raw = (form[f.key] ?? "").trim();
    if (!raw) {
      if (f.required) errors[f.key] = "Required.";
      continue;
    }
    const n = Number(raw);
    if (!Number.isFinite(n) || (f.type === "int" && !Number.isInteger(n)) || n <= 0 || (f.min != null && n < f.min)) {
      errors[f.key] = f.type === "usd" ? "Enter an amount above $0." : "Enter a whole number above 0.";
      continue;
    }
    params[f.key] = n;
  }
  if (kind === "agent_task" && !Object.keys(params).length && !Object.keys(errors).length) {
    errors.max_calls = "Set at least one cap.";
  }
  return { params, errors };
}

/** API params back to form strings, for editing. */
export function paramsToForm(kind: string, params: Record<string, unknown>): { form: Record<string, string>; models: string[] } {
  const form: Record<string, string> = {};
  let models: string[] = [];
  for (const f of ruleKindSpec(kind)?.fields ?? []) {
    const v = params[f.key];
    if (f.type === "models") models = Array.isArray(v) ? (v as string[]) : [];
    else if (f.type === "patterns") form[f.key] = Array.isArray(v) ? (v as string[]).join("\n") : "";
    else form[f.key] = v == null ? "" : String(v);
  }
  return { form, models };
}
