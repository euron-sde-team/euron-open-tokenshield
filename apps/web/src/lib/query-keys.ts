/**
 * Query keys in one place, so invalidation after a mutation names exactly what it
 * touched. Analytics keys carry the range and project filter.
 */
export const qk = {
  me: ["auth", "me"] as const,
  system: ["system"] as const,
  users: ["users"] as const,
  teams: ["teams"] as const,
  projects: (includeArchived = false) => ["projects", { includeArchived }] as const,
  projectsAll: ["projects"] as const,
  project: (id: string) => ["projects", "detail", id] as const,
  keys: (projectId?: string, includeRevoked = false) => ["keys", { projectId, includeRevoked }] as const,
  keysAll: ["keys"] as const,
  providers: ["providers"] as const,
  models: ["models"] as const,
  prices: (modelId: string) => ["models", "prices", modelId] as const,
  budgets: ["budgets"] as const,
  policies: ["policies"] as const,
  cacheStats: ["cache", "stats"] as const,
  cacheEntries: (projectId?: string) => ["cache", "entries", { projectId }] as const,
  cacheAll: ["cache"] as const,
  events: (filters: object) => ["usage", "events", filters] as const,
  event: (requestId: string) => ["usage", "event", requestId] as const,
  usageAll: ["usage"] as const,
  overview: (range: string, projectId?: string) => ["analytics", "overview", range, projectId ?? null] as const,
  timeseries: (range: string, projectId?: string) => ["analytics", "timeseries", range, projectId ?? null] as const,
  breakdown: (by: string, range: string, projectId?: string) =>
    ["analytics", "breakdown", by, range, projectId ?? null] as const,
  tasks: (range: string, projectId?: string) => ["analytics", "tasks", range, projectId ?? null] as const,
  analyticsAll: ["analytics"] as const,
  exports: ["exports"] as const,
  alerts: (includeAcknowledged = false) => ["alerts", { includeAcknowledged }] as const,
  alertsAll: ["alerts"] as const,
  audit: (action?: string) => ["audit", { action }] as const,
};

/** staleTime per kind of data, chosen deliberately (see docs PLAN caching layers). */
export const STALE = {
  analytics: 10_000,
  config: 30_000,
  requestsLive: 5_000,
  static: 5 * 60_000,
} as const;
