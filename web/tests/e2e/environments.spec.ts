import { expect, test } from "@playwright/test";
import { ENVS_URL, EXPORT_FILE } from "./envs";

// One branch per environment (main, env/uat, env/egma, env/bench) with the map derived, env/bench
// checked out. uat is ahead, and bench runs one job as an administrator: the map has two answers
// for the user of uat. The refresh comes last: it checks another branch out.
const TOKEN = process.env.CTMCHAIN_E2E_TOKEN ?? "e2e-token";
const at = (path: string) => `${ENVS_URL}${path}${path.includes("?") ? "&" : "?"}token=${TOKEN}`;

test("the map: the environments, their branches and the entries", async ({ page }) => {
  await page.goto(at("/map"));

  await expect(page.getByRole("heading", { level: 1, name: "Environment map" })).toBeVisible();
  const environments = page.getByRole("table", { name: "Environments" });
  await expect(environments.getByRole("row", { name: /bench/ })).toContainText("env/bench");
  const entries = page.getByRole("table", { name: "Map entries" });
  await expect(entries.getByRole("row", { name: /run_as\.2/ })).toContainText("abp77adm");

  await page.getByRole("button", { name: "Look at the branches" }).click();
  await expect(page.getByText(/Nothing new/)).toBeVisible();
});

test("between two environments: an entry preferred, an item packaged for the base's", async ({
  page,
}) => {
  await page.goto(at("/compare?base=env/bench&head=env/uat"));

  const between = page.getByRole("region", { name: "Between environments" });
  await expect(between).toContainText("uat is read in the terms of bench");
  const warnings = between.getByRole("list", { name: "Translation warnings" });
  await expect(warnings).toContainText("kept as it is");
  await between.getByRole("button", { name: "Prefer run_as.2" }).click();
  await expect(warnings).toHaveCount(0);

  await page.getByRole("button", { name: /^P77_NEW added/ }).click();
  await page.getByRole("checkbox", { name: "Take the whole job P77_CHAIN/P77_NEW" }).check();
  await page.getByRole("button", { name: "Package 1 item for bench" }).click();

  const panel = page.getByRole("region", { name: "Import package" });
  await expect(panel.getByRole("heading", { name: "Import package for bench" })).toBeVisible();
  await expect(panel).toContainText("job P77_NEW added");
  const href = await panel.getByRole("link", { name: /Download/ }).getAttribute("href");
  const xml = await (await page.request.get(`${ENVS_URL}${href}`)).text();
  // as bench has it: its letter, and the user of the entry that was preferred
  expect(xml).toMatch(
    /JOBNAME="BP77_NEW"[^>]*RUN_AS="abp77adm"|RUN_AS="abp77adm"[^>]*JOBNAME="BP77_NEW"/,
  );
  expect(xml).not.toContain("UP77");

  await page.getByRole("button", { name: "Take 1 change into env/bench" }).click();
  await expect(page.getByRole("dialog", { name: "Review change" })).toBeVisible();
});

test("a refresh: the export previewed, then the branch of its environment overwritten", async ({
  page,
}) => {
  await page.goto(at("/refresh"));
  await page.getByLabel("Export file").setInputFiles(EXPORT_FILE);
  await page.getByRole("button", { name: "Preview" }).click();

  await expect(page.getByRole("heading", { name: /is an export of uat/ })).toBeVisible();
  const differs = page.getByRole("region", { name: "What differs" });
  await expect(differs.getByRole("button", { name: /^P77_A modified/ })).toBeVisible();

  await page.getByRole("button", { name: "Overwrite env/uat…" }).click();
  await page.getByRole("button", { name: "Yes, overwrite env/uat" }).click();
  await expect(page.getByRole("status")).toContainText("env/uat now holds this export (commit");

  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByText(/Nothing differs: env\/uat already holds this export/)).toBeVisible();
});
