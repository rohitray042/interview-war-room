import { test, expect } from "@playwright/test";
const resume =
  "Browser Candidate\nSUMMARY\nData Engineer with 4 years of experience.\nSKILLS\nPython, SQL, Snowflake\nEXPERIENCE\n- Built Snowflake streams and tasks.\nEDUCATION\nBTech Computer Science";
test("upload, edit, add, delete, confirm, compare, evidence, refresh and revisions", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Resume & JD", exact: true }).click();
  await page.getByLabel("Upload resume file").setInputFiles({
    name: "browser-resume.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(resume),
  });
  await expect(
    page.getByText(
      "Text extracted locally. Review the items and their evidence.",
    ),
  ).toBeVisible();
  await page.getByLabel("Section", { exact: true }).selectOption("name");
  await page.getByLabel("Value 1", { exact: true }).fill("Reviewed Candidate");
  await page.getByRole("button", { name: "Save review", exact: true }).click();
  await expect(page.getByText("Review saved.")).toBeVisible();
  await page.getByLabel("Section", { exact: true }).selectOption("skills");
  await page.getByRole("button", { name: "Add item", exact: true }).click();
  await page.getByLabel("Value 1", { exact: true }).fill("Rust");
  await page
    .getByRole("button", { name: "Delete item 1", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm resume", exact: true })
    .click();
  await expect(
    page.getByText("Resume confirmed. This revision is now locked."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Job description", exact: true })
    .click();
  await page.getByText("Paste job description", { exact: true }).click();
  await page
    .getByLabel("Document text")
    .fill(
      "Must have\nSnowflake\nPython\nKafka\nGood to have\nAWS\nNice to have\nDatabricks",
    );
  await page.getByRole("button", { name: "Extract text", exact: true }).click();
  await expect(
    page.getByText("Extracted locally. Review before confirming."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Compare resume & JD", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Confirm JD", exact: true }).click();
  await page
    .getByRole("button", { name: "Compare resume & JD", exact: true })
    .click();
  const map = page.getByRole("region", { name: "Preparation map" });
  await expect(map).toBeVisible();
  const kafka = map
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: "Kafka", exact: true }) });
  await expect(kafka).toContainText("Missing");
  await expect(kafka).toContainText("HIGH PRIORITY");
  await expect(kafka.locator("details")).toHaveAttribute("open", "");
  await expect(kafka).toContainText("No matching excerpt found");
  await expect(kafka.locator("blockquote")).toContainText("Kafka");
  for (const topic of ["Snowflake", "Python"]) {
    const row = map.locator("article").filter({
      has: page.getByRole("heading", { name: topic, exact: true }),
    });
    await expect(row.locator("blockquote").first()).toBeVisible();
    await expect(row).toContainText("Document ");
    await expect(row).toContainText("Job description");
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: "test-results/analyzer-desktop.png",
    fullPage: true,
  });
  await page.reload();
  await page.getByRole("button", { name: "Resume & JD", exact: true }).click();
  await expect(map).toBeVisible();
  await page.getByLabel("Section", { exact: true }).selectOption("name");
  await expect(page.getByLabel("Value 1", { exact: true })).toHaveValue(
    "Reviewed Candidate",
  );
  await page
    .getByRole("button", { name: "Create editable revision", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Confirm resume", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Compare resume & JD", exact: true }),
  ).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/analyzer-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
