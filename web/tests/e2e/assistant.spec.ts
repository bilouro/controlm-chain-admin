import { expect, test, type Locator, type Page } from "@playwright/test";

// A real conversation: Kilo, the controlm agent and a model (CTMCHAIN_E2E_MODEL). The model's
// words vary; the tests check what the tools did and what the repository holds.
const TOKEN = process.env.CTMCHAIN_E2E_TOKEN ?? "e2e-token";
const LONG = { timeout: 240_000 };

test.skip(process.env.CTMCHAIN_E2E_ASSISTANT !== "1", "needs Kilo and a model");

async function open(page: Page) {
  await page.goto(`/?token=${TOKEN}`);
  const toggle = page.getByRole("button", { name: "Assistant" });
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  const panel = page.getByRole("complementary", { name: "Assistant" });
  await expect(panel.getByRole("textbox", { name: "Message" })).toBeVisible();
  return panel;
}

async function ask(panel: Locator, text: string) {
  const box = panel.getByRole("textbox", { name: "Message" });
  await expect(box).toBeEnabled();
  await box.fill(text);
  await box.press("Enter");
  await expect(panel.getByRole("log", { name: "Conversation" })).toContainText(text);
}

/** Wait until the assistant asks for an approval; a model that asks in words gets a yes. */
async function approvalOf(panel: Locator): Promise<Locator> {
  const waiting = panel.getByRole("region", { name: "Waiting for your approval" });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await expect(async () => {
      const asked = await waiting.isVisible();
      const idle = (await panel.getByRole("status").count()) === 0;
      expect(asked || idle).toBe(true);
    }).toPass(LONG);
    if (await waiting.isVisible()) return waiting;
    await ask(panel, "Yes, apply it.");
  }
  await expect(waiting).toBeVisible(LONG);
  return waiting;
}

async function maxwait(page: Page): Promise<string | undefined> {
  const job = (await (await page.request.get("/api/jobs/P77_CHAIN/P77_B")).json()) as {
    raw: Record<string, unknown>;
  };
  return job.raw.MAXWAIT as string | undefined;
}

test("a question, a change approved, a change rejected", async ({ page }) => {
  const panel = await open(page);
  const log = panel.getByRole("log", { name: "Conversation" });

  await ask(panel, "Which condition does the job P77_B wait for? Answer in one line.");
  await expect(
    log.getByRole("listitem", { name: /^Tool (find|show|condition): completed/ }).first(),
  ).toBeVisible(LONG);
  await expect(panel.getByRole("status")).toHaveCount(0, LONG);
  await expect(log).toContainText("P77_A-P77_B_OK");

  await ask(panel, "Set MAXWAIT to 3 on the job P77_B.");
  const waiting = await approvalOf(panel);
  await expect(waiting).toContainText("MAXWAIT");
  await expect(waiting).toContainText("P77_CHAIN/P77_B");
  expect(await maxwait(page)).toBeUndefined();
  await waiting.getByRole("button", { name: "Apply" }).click();
  await expect(log.getByRole("listitem", { name: "Tool apply: completed" })).toBeVisible(LONG);
  expect(await maxwait(page)).toBe("3");

  await page.goto("/folders/P77_CHAIN/jobs/P77_B");
  const again = page.getByRole("complementary", { name: "Assistant" });
  await expect(again.getByRole("log", { name: "Conversation" })).toContainText("MAXWAIT");
  await expect(again.getByRole("status")).toHaveCount(0, LONG);

  await ask(again, "Now set MAXWAIT to 7 on the job P77_B.");
  const second = await approvalOf(again);
  await expect(second).toContainText("7");
  await second.getByRole("button", { name: "Reject" }).click();
  await expect(second).toHaveCount(0, LONG);
  await expect(again.getByRole("status")).toHaveCount(0, LONG);
  expect(await maxwait(page)).toBe("3");
});
