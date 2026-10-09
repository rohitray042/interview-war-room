import { test, expect } from "@playwright/test";

test("question bank filters, details, bookmarks, status, grounded generation and duplicates", async ({
  page,
  request,
}) => {
  const ids: string[] = [];
  for (const [kind, text] of [
    [
      "resume",
      "Bank Candidate\nSKILLS\nPython\nEXPERIENCE\n- Built Snowflake pipelines.",
    ],
    ["jd", "Must have\nKafka\nSnowflake\nPython"],
  ]) {
    const response = await request.post("/api/v1/documents/text", {
      data: { kind, text },
    });
    const bundle = await response.json();
    const analysis = bundle.analyses[0];
    await request.post(`/api/v1/analyses/${analysis.id}/confirm`, {
      data: { revision: analysis.revision },
    });
    ids.push(analysis.id);
  }
  const target = await request.post("/api/v1/targets", {
    data: { resume_id: ids[0], jd_id: ids[1] },
  });
  expect(target.ok()).toBeTruthy();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "Question bank", exact: true })
    .click();
  await page
    .getByLabel("Filter Category", { exact: true })
    .selectOption("Kafka");
  await expect(page.locator(".bank-list article")).toHaveCount(3);
  await page.getByLabel("Search questions").fill("offset");
  await expect(page.locator(".bank-list article")).toHaveCount(1);
  await page.locator(".question-open").click();
  const detail = page.getByRole("region", { name: "Question details" });
  await expect(detail).toContainText("Expected topics");
  await detail
    .getByRole("button", { name: "Bookmark question", exact: true })
    .click();
  await detail.getByLabel("Question status").selectOption("needs_review");
  await expect(detail.getByLabel("Question status")).toHaveValue(
    "needs_review",
  );
  await page.getByLabel("Saved questions", { exact: true }).check();
  await expect(page.locator(".bank-list article")).toHaveCount(1);
  await page.reload();
  await page
    .getByRole("button", { name: "Question bank", exact: true })
    .click();
  await page.getByLabel("Saved questions", { exact: true }).check();
  await page.locator(".question-open").click();
  await expect(detail.getByLabel("Question status")).toHaveValue(
    "needs_review",
  );
  await page
    .getByRole("button", { name: "Generate personalized questions" })
    .click();
  const form = page.locator(".bank-generation");
  await form.getByLabel("Category", { exact: true }).selectOption("Kafka");
  await form.getByLabel("Number of questions").fill("1");
  await form.getByRole("checkbox").check();
  await form.getByRole("button", { name: "Generate set", exact: true }).click();
  await expect(
    page.getByText("1 created; 0 existing questions reused."),
  ).toBeVisible();
  await expect(detail).toContainText("resume coverage: missing");
  await expect(detail).toContainText("No matching excerpt found");
  await expect(detail.locator("blockquote")).toContainText("Kafka");
  await page
    .getByRole("button", { name: "Generate personalized questions" })
    .click();
  await form.getByRole("button", { name: "Generate set", exact: true }).click();
  await expect(
    page.getByText("1 created; 0 existing questions reused."),
  ).toBeVisible();
  await expect(page.locator(".bank-list")).toHaveAttribute(
    "aria-busy",
    "false",
  );
  await expect(page.locator(".bank-list article")).toHaveCount(2);
  await expect(page.locator(".bank-summary")).toContainText("38");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: "test-results/questions-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/questions-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
