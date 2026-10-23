/** Plain-words explanations for the gateway's vocabulary, shown as inline hints. */
export const GLOSSARY = {
  hardBudget:
    "Hard budget: blocks a request before it reaches the provider when its worst-case cost would push spend past the limit.",
  softBudget: "Soft budget: never blocks. It raises an alert at the threshold so someone can act.",
  reservation:
    "Before calling the provider, TokenShield reserves the worst-case cost against every matching budget at once, then settles it to the actual cost. Concurrent requests can never overspend.",
  coalescing:
    "When identical requests arrive at the same time, only one goes upstream; the others wait and share its answer.",
  uncertain:
    "The provider timed out, so the true cost is unknown. The reservation stays held until the background sweep reconciles it. It is never recorded as free.",
  cacheScope:
    "Cache entries never cross projects. With a user scope, one end user is never served another user's cached answer.",
  spendAvoided: "What cache hits would have cost at current prices. Money that never left your account.",
  cacheHitRate: "Share of requests answered from cache, with zero upstream calls.",
  rejected: "Requests TokenShield blocked before any upstream call: budgets, rate limits or policies.",
  priceVersion:
    "Prices are versioned. Every request keeps the price version it was charged at, so publishing a new price never rewrites history.",
  estimated:
    "Estimated cost is computed before the call from the prompt and the maximum output allowed. Actual cost uses the tokens the provider reported.",
  alertThreshold: "Percentage of the limit at which an alert fires, for hard and soft budgets alike.",
  nondeterministic:
    "By default only temperature 0 requests are cached, because other answers are meant to vary. Turn on to cache those too.",
  unpriced: "No price is published for this model, so its spend cannot be checked against hard budgets. Requests to it are blocked by hard budgets until priced.",
  restricted: "Restricted models can only be used by projects that list them as allowed.",
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
