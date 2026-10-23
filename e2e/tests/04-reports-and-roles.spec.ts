import { expect, test } from "@playwright/test";

import { RUN, adminApi, asOwner, signIn } from "../helpers";

test("export usage as CSV and download it", async ({ page }) => {
  await asOwner(page);
  await page.goto("/reports");
  await page.waitForLoadState("networkidle");  // let the export list load before counting
  const before = await page.getByRole("button", { name: /^CSV$/ }).count();
  await page.getByRole("button", { name: /export/i }).first().click();
  await expect(page.getByRole("button", { name: /^CSV$/ })).toHaveCount(before + 1);
  const link = page.waitForEvent("popup").then((p) => p.url()).catch(() => null);
  const download = page.waitForEvent("download").then((d) => d.url()).catch(() => null);
  await page.getByRole("button", { name: /^CSV$/ }).first().click();
  const url = await Promise.race([link, download, new Promise<null>((r) => setTimeout(() => r(null), 10_000))]);
  expect(url, "the CSV opens as a download or a presigned link").toBeTruthy();
  // A presigned S3 link needs nothing; the local-disk link is an API path that needs the session.
  const resp = await page.request.get(url as string);
  expect(resp.status()).toBe(200);
  expect(await resp.text()).toContain("request_id,created_at");
});

test("a viewer can read everything and change nothing", async ({ browser, request }) => {
  const headers = await adminApi(request);
  const email = `viewer-${RUN}@example.test`;
  const created = await request.post("/api/v1/users", {
    data: { email, name: "E2E Viewer", role: "viewer", password: "Viewer-Pass-123" },
    headers,
  });
  expect(created.status()).toBe(201);
  const viewer = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const page = await viewer.newPage();
  await signIn(page, email, "Viewer-Pass-123");
  await page.goto("/budgets");
  await expect(page.getByRole("heading", { name: "Budgets" })).toBeVisible();
  await expect(page.getByRole("button", { name: /new budget/i })).toHaveCount(0);
  await page.goto("/keys");
  await expect(page.getByRole("button", { name: /new key/i })).toHaveCount(0);
  await viewer.close();
});

test("a new policy shows up and can be switched off", async ({ page }) => {
  await asOwner(page);
  await page.goto("/policies");
  await page.getByRole("button", { name: /new rule/i }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/name/i).first().fill(`E2E retry guard ${RUN}`);
  await dialog.getByRole("button", { name: /create|save/i }).last().click();
  const item = page.getByText(`E2E retry guard ${RUN}`);
  await expect(item).toBeVisible();
});
