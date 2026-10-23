/**
 * One mapping from request and cache states to a chip tone, label and explanation, so a
 * status reads the same on the request log, the drawer, the playground and the overview.
 */

export type Tone = "success" | "savings" | "info" | "primary" | "warning" | "danger" | "neutral";

export interface ChipSpec {
  label: string;
  tone: Tone;
  hint: string;
}

const STATUS: Record<string, ChipSpec> = {
  SUCCESS: { label: "Success", tone: "success", hint: "The request completed and its cost was recorded." },
  REJECTED: {
    label: "Rejected",
    tone: "warning",
    hint: "TokenShield blocked the request before any upstream call: a budget, limit or policy said no.",
  },
  ERROR: { label: "Error", tone: "danger", hint: "The upstream provider failed. Any budget reservation was released." },
  UNCERTAIN: {
    label: "Uncertain",
    tone: "primary",
    hint: "The upstream timed out, so the true cost is unknown. The reservation stays held until the sweep reconciles it, never assumed zero.",
  },
};

const CACHE: Record<string, ChipSpec> = {
  HIT: { label: "Hit", tone: "savings", hint: "Served from cache with zero upstream calls. The cost it would have had counts as spend avoided." },
  MISS: { label: "Miss", tone: "neutral", hint: "Eligible for cache but not found, so it went upstream and was stored." },
  COALESCED: {
    label: "Coalesced",
    tone: "info",
    hint: "An identical request was already in flight, so this one waited and shared its answer: one upstream call for both.",
  },
  BYPASS: { label: "Bypass", tone: "neutral", hint: "Not cache eligible: cache off, sensitive, non-deterministic or rejected first." },
  SEMANTIC_HIT: { label: "Semantic hit", tone: "savings", hint: "Served from the semantic cache: a close enough earlier prompt." },
};

function fallback(value: string): ChipSpec {
  const label = value ? value.charAt(0) + value.slice(1).toLowerCase().replace(/_/g, " ") : "Unknown";
  return { label, tone: "neutral", hint: "" };
}

export function statusChip(status: string | null | undefined): ChipSpec {
  const key = (status ?? "").toUpperCase();
  return STATUS[key] ?? fallback(key);
}

export function cacheChip(cacheStatus: string | null | undefined): ChipSpec {
  const key = (cacheStatus ?? "").toUpperCase();
  return CACHE[key] ?? fallback(key);
}

export const REQUEST_STATUSES = Object.keys(STATUS);
export const CACHE_STATUSES = ["HIT", "MISS", "COALESCED", "BYPASS"];

/** Rule codes the gateway writes into usage events, in plain words. */
const RULE_LABEL: Record<string, string> = {
  budget_exceeded: "Budget exceeded",
  model_unpriced: "Model has no price",
  retry_storm: "Retry storm",
  prompt_too_large: "Prompt too large",
  context_length_exceeded: "Context window exceeded",
  output_limit_exceeded: "Output limit exceeded",
  agent_call_limit: "Agent call limit",
  agent_cost_limit: "Agent cost limit",
  agent_loop_detected: "Agent loop detected",
  agent_deadline: "Agent deadline",
  model_restricted: "Restricted model",
  model_not_allowed: "Model not allowed",
  model_not_found: "Unknown model",
  prompt_injection_suspected: "Prompt injection",
  rpm_limit: "Requests per minute",
  tpm_limit: "Tokens per minute",
  concurrency_limit: "Concurrency limit",
  invalid_request: "Invalid request",
  invalid_json: "Invalid JSON",
  budget_service_unavailable: "Budget service down",
  policy_service_unavailable: "Policy service down",
  rate_limiter_unavailable: "Rate limiter down",
};

export function ruleLabel(rule: string | null | undefined): string {
  if (!rule) return "";
  return RULE_LABEL[rule] ?? rule.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Severity of an alert as a tone. */
export function severityTone(severity: string | null | undefined): Tone {
  switch ((severity ?? "").toLowerCase()) {
    case "critical":
      return "danger";
    case "warning":
      return "warning";
    case "info":
      return "info";
    default:
      return "neutral";
  }
}

/** Budget risk from used percentage and the alert threshold. */
export function budgetRisk(usedPct: number | null | undefined, thresholdPct = 80): "ok" | "warn" | "over" {
  if (usedPct == null) return "ok";
  if (usedPct >= 100) return "over";
  if (usedPct >= thresholdPct) return "warn";
  return "ok";
}
