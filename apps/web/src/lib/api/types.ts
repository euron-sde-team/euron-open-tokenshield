/**
 * Named aliases over the generated OpenAPI types (`pnpm gen:api`). Nothing here is
 * hand-written: every shape comes from `schema.d.ts`, which is generated from
 * docs/api/openapi.yaml.
 */
import type { components, operations } from "./schema";

type S = components["schemas"];

export type User = S["UserOut"];
export type UserCreate = S["UserCreate"];
export type UserUpdate = S["UserUpdate"];
export type Session = S["SessionOut"];
export type Team = S["TeamOut"];
export type TeamIn = S["TeamIn"];
export type TeamUpdate = S["TeamUpdate"];
export type Project = S["ProjectOut"];
export type ProjectIn = S["ProjectIn"];
export type ProjectUpdate = S["ProjectUpdate"];
export type ApiKey = S["KeyOut"];
export type ApiKeyCreated = S["KeyCreated"];
export type ApiKeyIn = S["KeyIn"];
export type Provider = S["ProviderOut"];
export type ProviderIn = S["ProviderIn"];
export type ProviderUpdate = S["ProviderUpdate"];
export type ProviderTest = S["ProviderTest"];
export type Model = S["ModelOut"];
export type ModelIn = S["ModelIn"];
export type ModelUpdate = S["ModelUpdate"];
export type Price = S["PriceOut"];
export type PriceIn = S["PriceIn"];
export type Budget = S["BudgetOut"];
export type BudgetIn = S["BudgetIn"];
export type BudgetUpdate = S["BudgetUpdate"];
export type Rule = S["RuleOut"];
export type RuleIn = S["RuleIn"];
export type RuleUpdate = S["RuleUpdate"];
export type CacheStats = S["CacheStats"];
export type CacheEntry = S["CacheEntryOut"];
export type UsageEvent = S["UsageEventOut"];
export type UsageEventDetail = S["UsageEventDetail"];
export type UsagePage = S["Page_UsageEventOut_"];
export type Reservation = S["ReservationOut"];
export type Reconciliation = S["ReconciliationOut"];
export type Overview = S["Overview"];
export type Totals = S["Totals"];
export type SeriesPoint = S["SeriesPoint"];
export type BreakdownRow = S["BreakdownRow"];
export type TaskSummary = S["TaskSummary"];
export type ExportJob = S["ExportOut"];
export type ExportIn = S["ExportIn"];
export type ExportDownload = S["ExportDownload"];
export type Alert = S["AlertOut"];
export type AlertList = S["AlertList"];
export type AuditEntry = S["AuditOut"];
export type AuditPage = S["Page_AuditOut_"];
export type PlaygroundRequest = S["PlaygroundRequest"];
export type SystemInfo = S["SystemInfo"];

export type RangeKey = NonNullable<S["ExportIn"]["range"]>;
export type BudgetScopeType = BudgetIn["scope_type"];
export type BudgetPeriod = BudgetIn["period"];
export type BudgetMode = NonNullable<BudgetIn["mode"]>;
export type RuleKind = RuleIn["kind"];
export type RuleAction = NonNullable<RuleIn["action"]>;
export type RuleScopeType = NonNullable<RuleIn["scope_type"]>;
export type Role = NonNullable<UserCreate["role"]>;
export type BreakdownBy = NonNullable<
  NonNullable<operations["breakdown_api_v1_analytics_breakdown_get"]["parameters"]["query"]>["by"]
>;
export type UsageEventFilters = NonNullable<
  operations["list_events_api_v1_usage_events_get"]["parameters"]["query"]
>;
