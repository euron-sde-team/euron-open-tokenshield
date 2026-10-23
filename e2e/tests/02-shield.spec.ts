import { expect, test } from "@playwright/test";

import { RUN, asOwner, choose } from "../helpers";

/**
 * The core journey: create a project, a key and a hard budget in the dashboard, call the
 * gateway with the key exactly as an application would, then watch TokenShield account
 * for it, serve a repeat from cache, and block the request that would overspend.
 */
test.describe.serial("shield a new project", () => {
  const project = `E2E Shop ${RUN}`;
  let key = "";

  test("create project, key and hard budget", async ({ page }) => {
    await asOwner(page);
    await page.goto("/projects");
    await page.getByRole("button", { name: /new project/i }).click();
    await page.locator("#project-name").fill(project);
    await page.locator("#project-desc").fill("Checkout assistant");
    await page.getByRole("button", { name: /create project/i }).click();
    await expect(page.getByText(project).first()).toBeVisible();

    await page.goto("/keys");
    await page.getByRole("button", { name: /new key/i }).click();
    await choose(page, "key-project", project);
    await page.locator("#key-name").fill("e2e");
    await page.getByRole("button", { name: /create key/i }).click();
    key = (await page.getByTestId("new-key").textContent())?.trim() ?? "";
    expect(key).toMatch(/^tsk_[0-9a-f]{12}_/);
    await page.keyboard.press("Escape");

    await page.goto("/budgets");
    await page.getByRole("button", { name: /new budget/i }).click();
    await page.locator("#budget-name").fill(`E2E cap ${RUN}`);
    await choose(page, "budget-scope-type", /project/i);
    await choose(page, "budget-scope", project);
    // Fits one worst-case chat-small reservation (about $0.0006), not a chat-large one.
    await page.locator("#budget-limit").fill("0.002");
    await page.getByRole("button", { name: /create budget/i }).click();
    await expect(page.getByText(`E2E cap ${RUN}`)).toBeVisible();
  });

  test("an OpenAI-style call is attributed, priced and cached", async ({ page, request }) => {
    const body = { model: "chat-small", temperature: 0, messages: [{ role: "user", content: `What is photosynthesis? ${RUN}` }] };
    const first = await request.post("/v1/chat/completions", { data: body, headers: { authorization: `Bearer ${key}` } });
    expect(first.status()).toBe(200);
    expect(first.headers()["x-tokenshield-cache"]).toBe("MISS");
    const rid = first.headers()["x-tokenshield-request-id"];
    const second = await request.post("/v1/chat/completions", { data: body, headers: { authorization: `Bearer ${key}` } });
    expect(second.headers()["x-tokenshield-cache"]).toBe("HIT");

    await asOwner(page);
    await page.goto(`/requests?q=${rid}`);
    const row = page.getByText(rid.slice(0, 16));
    await expect(row).toBeVisible();
    await expect(page.getByText("Success").first()).toBeVisible();
    await row.click();
    const drawer = page.getByRole("dialog");
    await expect(drawer.getByText(rid)).toBeVisible();
    await expect(drawer.getByText(`E2E cap ${RUN}`)).toBeVisible();
    await expect(drawer.getByText(/settled/i).first()).toBeVisible();
  });

  test("the request that would overspend is blocked before the provider", async ({ page, request }) => {
    const resp = await request.post("/v1/chat/completions", {
      data: { model: "chat-large", messages: [{ role: "user", content: `Write a long report ${RUN}` }], max_tokens: 2000 },
      headers: { authorization: `Bearer ${key}` },
    });
    expect(resp.status()).toBe(402);
    const err = (await resp.json()).error;
    expect(err.code).toBe("budget_exceeded");

    await asOwner(page);
    // Filters live in the URL, so a filtered view is a shareable link.
    await page.goto("/requests?status=REJECTED");
    await expect(page.getByText("Budget exceeded").first()).toBeVisible();
  });
});
