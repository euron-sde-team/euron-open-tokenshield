import { describe, expect, it } from "vitest";

import { budgetRisk, cacheChip, ruleLabel, severityTone, statusChip } from "@/lib/chips";
import { bucketUnit, isRangeKey, previousPeriodLabel, rangeLabel, rangeMs, rangeStart } from "@/lib/range";
import { canManageUsers, canWrite, isRole, roleLabel } from "@/lib/roles";

describe("chips", () => {
  it("maps every request status and cache result", () => {
    expect(statusChip("SUCCESS").tone).toBe("success");
    expect(statusChip("rejected").label).toBe("Rejected");
    expect(statusChip("UNCERTAIN").hint).toMatch(/never assumed zero/);
    expect(cacheChip("HIT").tone).toBe("savings");
    expect(cacheChip("COALESCED").label).toBe("Coalesced");
    expect(cacheChip("SOMETHING_NEW").label).toBe("Something new");
  });

  it("labels every rule code the gateway emits", () => {
    const codes = [
      "budget_exceeded", "model_unpriced", "retry_storm", "prompt_too_large", "context_length_exceeded",
      "output_limit_exceeded", "agent_call_limit", "agent_cost_limit", "agent_loop_detected", "agent_deadline",
      "model_restricted", "model_not_allowed", "model_not_found", "prompt_injection_suspected", "rpm_limit",
      "tpm_limit", "concurrency_limit", "budget_service_unavailable",
    ];
    for (const code of codes) {
      expect(ruleLabel(code)).not.toContain("_");
    }
    expect(ruleLabel("agent_loop_detected")).toBe("Agent loop detected");
    expect(ruleLabel(null)).toBe("");
  });

  it("grades budget risk and alert severity", () => {
    expect(budgetRisk(50)).toBe("ok");
    expect(budgetRisk(80)).toBe("warn");
    expect(budgetRisk(74, 75)).toBe("ok");
    expect(budgetRisk(101)).toBe("over");
    expect(budgetRisk(null)).toBe("ok");
    expect(severityTone("critical")).toBe("danger");
    expect(severityTone("whatever")).toBe("neutral");
  });
});

describe("ranges", () => {
  it("knows its windows and labels", () => {
    expect(isRangeKey("7d")).toBe(true);
    expect(isRangeKey("1y")).toBe(false);
    expect(rangeMs("24h")).toBe(86_400_000);
    expect(rangeLabel("30d")).toBe("Last 30 days");
    expect(previousPeriodLabel("7d")).toBe("vs prior 7d");
    expect(bucketUnit("24h")).toBe("hour");
    expect(bucketUnit("7d")).toBe("day");
    expect(rangeStart("1h", new Date("2026-10-23T10:00:00Z")).toISOString()).toBe("2026-10-23T09:00:00.000Z");
  });
});

describe("roles", () => {
  it("gates writes and user management", () => {
    expect(canWrite("admin")).toBe(true);
    expect(canWrite("viewer")).toBe(false);
    expect(canManageUsers("admin")).toBe(false);
    expect(canManageUsers("owner")).toBe(true);
    expect(isRole("root")).toBe(false);
    expect(roleLabel("viewer")).toBe("Viewer");
    expect(roleLabel(undefined)).toBe("Unknown");
  });
});
