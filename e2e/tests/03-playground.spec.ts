import { expect, test } from "@playwright/test";

import { RUN, asOwner, choose } from "../helpers";

test("playground runs through the pipeline and shows the cache result", async ({ page }) => {
  await asOwner(page);
  await page.goto("/playground");
  await choose(page, "pg-project", "Alpha Tutor");
  await choose(page, "pg-model", "chat-small");
  await page.locator("#pg-user").fill(`Explain the water cycle (${RUN})`);
  await page.getByRole("button", { name: /send request/i }).click();
  await expect(page.getByText(/water cycle/i).last()).toBeVisible();
  await expect(page.getByText(/^MISS$|Miss/).first()).toBeVisible();
  await page.getByRole("button", { name: /send request/i }).click();
  await expect(page.getByText(/^HIT$|Hit/).first()).toBeVisible();
});

test("playground renders a policy rejection with its details", async ({ page }) => {
  await asOwner(page);
  await page.goto("/playground");
  await choose(page, "pg-project", "Marketing Studio");
  await choose(page, "pg-model", "experimental-xl");
  await page.getByRole("button", { name: /send request/i }).click();
  await expect(page.getByText(/restricted/i).first()).toBeVisible();
});
