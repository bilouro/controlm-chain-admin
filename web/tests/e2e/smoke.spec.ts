import { expect, test } from "@playwright/test";

const TOKEN = process.env.CTMCHAIN_E2E_TOKEN ?? "e2e-token";

test("the chains, a folder, a job and the findings", async ({ page }) => {
  await page.goto(`/?token=${TOKEN}`);
  await expect(page.getByRole("link", { name: "P77_CHAIN" }).first()).toBeVisible();

  await page.goto("/folders/P77_CHAIN");
  await expect(page.getByRole("heading", { level: 1, name: "P77_CHAIN" })).toBeVisible();

  await page.goto("/folders/P77_CHAIN/jobs/P77_B");
  await expect(page.getByRole("heading", { level: 1, name: "P77_B" })).toBeVisible();

  await page.goto("/validate");
  await expect(page.getByRole("heading", { level: 1, name: "Validation" })).toBeVisible();
});

test("the assistant panel opens beside the page", async ({ page }) => {
  await page.goto(`/?token=${TOKEN}`);
  await page.getByRole("button", { name: "Assistant" }).click();

  const panel = page.getByRole("complementary", { name: "Assistant" });
  await expect(panel).toBeVisible();
  if (process.env.CTMCHAIN_E2E_ASSISTANT !== "1") {
    await expect(panel).toContainText("ctmchain serve --assistant");
  } else {
    await expect(panel.getByRole("textbox", { name: "Message" })).toBeVisible();
  }
});
