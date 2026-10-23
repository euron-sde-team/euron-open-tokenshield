/**
 * Curated README screenshots and tour frames from a freshly seeded stack.
 *
 *   make up && make demo
 *   cd scripts/qa && QA_BASE=http://localhost:4110 node screenshots.mjs
 *   ../../scripts/qa/make-tour.sh        (stitches the frames into docs/assets/tour.gif)
 *
 * Writes docs/assets/screenshots/NN-name.png and scripts/qa/output/tour/NN.png.
 */
import { mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.QA_BASE ?? "http://localhost:4110";
const EMAIL = process.env.QA_EMAIL ?? "admin@tokenshield.local";
const PASSWORD = process.env.QA_PASSWORD ?? process.env.TS_DEMO_PASSWORD ?? "ShieldDemo2026";
const SHOTS = path.resolve(HERE, "../../docs/assets/screenshots");
const TOUR = path.resolve(HERE, "output/tour");
const CHROME = process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH) ? process.env.CHROME_PATH : undefined;
const DESKTOP = { width: 1440, height: 900, deviceScaleFactor: 1 };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let tourIndex = 0;

async function settle(page, ms = 1200) {
  await page.waitForNetworkIdle({ idleTime: 400, timeout: 20_000 }).catch(() => {});
  await sleep(ms);
}

async function shot(page, name, { tour = true, fullPage = false } = {}) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage });
  if (tour) await page.screenshot({ path: path.join(TOUR, `${String(++tourIndex).padStart(2, "0")}.png`) });
  console.log(`saved ${name}`);
}

async function choose(page, triggerId, label) {
  await page.click(`#${triggerId}`);
  await sleep(200);
  const options = await page.$$('[role="option"]');
  for (const o of options) {
    const text = (await o.evaluate((el) => el.textContent)) ?? "";
    if (text.trim().startsWith(label)) {
      await o.click();
      await sleep(200);
      return;
    }
  }
  throw new Error(`option ${label} not found in #${triggerId}`);
}

async function clickButton(page, text) {
  const buttons = await page.$$("button");
  for (const b of buttons) {
    const t = ((await b.evaluate((el) => el.textContent)) ?? "").trim();
    if (t.includes(text)) {
      await b.click();
      return;
    }
  }
  throw new Error(`button ${text} not found`);
}

async function main() {
  await mkdir(SHOTS, { recursive: true });
  await mkdir(TOUR, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  await page.setViewport(DESKTOP);
  await page.evaluateOnNewDocument(() => {
    try {
      localStorage.setItem("theme", "light");
    } catch {}
  });

  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await sleep(600);
  await shot(page, "00-sign-in", { tour: false });
  await page.type("#email", EMAIL);
  await page.type("#password", PASSWORD);
  await Promise.all([page.waitForNavigation({ waitUntil: "networkidle2" }), page.click("button[type=submit]")]);

  const projects = await page.evaluate(async () => (await (await fetch("/api/v1/projects")).json()));
  const id = (name) => projects.find((p) => p.name === name)?.id;

  await page.goto(`${BASE}/`, { waitUntil: "networkidle2" });
  await settle(page, 1800);
  await shot(page, "01-overview");

  await page.goto(`${BASE}/requests?project_id=${id("Alpha Tutor")}`, { waitUntil: "networkidle2" });
  await settle(page);
  await shot(page, "02-requests");

  // A paid request with budget reservations, opened in the drawer.
  await page.goto(`${BASE}/requests?project_id=${id("Alpha Tutor")}&cache_status=MISS&status=SUCCESS`, { waitUntil: "networkidle2" });
  await settle(page);
  await page.click("table tbody tr");
  await settle(page, 1000);
  await shot(page, "03-request-detail");

  await page.goto(`${BASE}/requests?status=REJECTED`, { waitUntil: "networkidle2" });
  await settle(page);
  await shot(page, "04-rejections");

  await page.goto(`${BASE}/budgets`, { waitUntil: "networkidle2" });
  await settle(page);
  await shot(page, "05-budgets");

  await page.goto(`${BASE}/policies`, { waitUntil: "networkidle2" });
  await settle(page);
  await shot(page, "06-policies");

  await page.goto(`${BASE}/playground`, { waitUntil: "networkidle2" });
  await settle(page);
  await choose(page, "pg-project", "Alpha Tutor");
  await choose(page, "pg-model", "chat-small");
  await page.click("#pg-user", { clickCount: 3 });
  await page.type("#pg-user", "Explain photosynthesis to a ten year old in two sentences.");
  await clickButton(page, "Send request");
  await settle(page, 1200);
  await clickButton(page, "Send request");
  await settle(page, 1200);
  await shot(page, "07-playground-cache-hit");

  await page.goto(`${BASE}/agents`, { waitUntil: "networkidle2" });
  await settle(page);
  await shot(page, "08-agents");

  await page.goto(`${BASE}/cache`, { waitUntil: "networkidle2" });
  await settle(page);
  await shot(page, "09-cache");

  await page.goto(`${BASE}/models`, { waitUntil: "networkidle2" });
  await settle(page);
  await shot(page, "10-models");

  await page.goto(`${BASE}/projects/${id("Alpha Tutor")}`, { waitUntil: "networkidle2" });
  await settle(page, 1600);
  await shot(page, "11-project");

  await page.goto(`${BASE}/keys`, { waitUntil: "networkidle2" });
  await settle(page);
  await shot(page, "12-api-keys", { tour: false });

  // Dark mode.
  await page.evaluate(() => localStorage.setItem("theme", "dark"));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle2" });
  await settle(page, 1800);
  await shot(page, "13-dark-mode");

  // Phone width.
  const phone = await ctx.newPage();
  await phone.setViewport({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await phone.evaluateOnNewDocument(() => {
    try {
      localStorage.setItem("theme", "light");
    } catch {}
  });
  await phone.goto(`${BASE}/`, { waitUntil: "networkidle2" });
  await settle(phone, 1800);
  await phone.screenshot({ path: path.join(SHOTS, "14-mobile.png") });
  console.log("saved 14-mobile");

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
